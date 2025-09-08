from flask import Flask, render_template, request, redirect, url_for, session, send_file
import mysql.connector
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import calendar
from datetime import date
import os

# Inicializar la aplicación de Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tu_clave_secreta_por_defecto')

# Configurar la conexión a la base de datos MySQL usando variables de entorno
db = mysql.connector.connect(
    host=os.environ.get('DB_HOST'),
    user=os.environ.get('DB_USER'),
    password=os.environ.get('DB_PASSWORD'),
    database=os.environ.get('DB_NAME'),
    port=int(os.environ.get('DB_PORT', 3306))
)

# Configurar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Lista de nombres de meses en español
NOMBRES_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

# Clase de Usuario para Flask-Login
class Usuario(UserMixin):
    def __init__(self, RUT, nombre_completo, email, rol, contraseña, servicio):
        self.id = RUT
        self.nombre = nombre_completo
        self.email = email
        self.rol = rol
        self.contraseña = contraseña
        self.servicio = servicio
    
    def tiene_rol(self, rol_requerido):
        return rol_requerido in self.rol

@login_manager.user_loader
def load_user(RUT):
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE RUT = %s", (RUT,))
    user_data = cursor.fetchone()
    cursor.close()
    if user_data:
        return Usuario(user_data['RUT'], user_data['nombre_completo'], user_data['email'], user_data['rol'], user_data['contraseña'], user_data['servicio'])
    return None

# RUTA PARA EL LOGIN
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        contraseña = request.form['contraseña']
        
        cursor = db.cursor(dictionary=True)
        query = "SELECT * FROM usuarios WHERE email = %s"
        cursor.execute(query, (email,))
        user_data = cursor.fetchone()
        cursor.close()

        if user_data and user_data['contraseña'] == contraseña:
            user = Usuario(user_data['RUT'], user_data['nombre_completo'], user_data['email'], user_data['rol'], user_data['contraseña'], user_data['servicio'])
            login_user(user)
            if 'administrador' in user.rol:
                return redirect(url_for('admin_view'))
            else:
                return redirect(url_for('empleado_view', RUT=user.id))
        
        return "Credenciales incorrectas"

    return render_template('login.html')

# RUTA PARA CERRAR SESIÓN
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# VISTA DEL ADMINISTRADOR: Muestra todos los registros de asistencia
@app.route('/admin')
@login_required
def admin_view():
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT u.nombre_completo, a.* FROM asistencias a JOIN usuarios u ON a.RUT = u.RUT")
    registros = cursor.fetchall()
    cursor.close()
    return render_template('admin.html', registros=registros)

# VISTA DEL EMPLEADO: Muestra solo sus propios registros
@app.route('/empleado/<string:RUT>')
@login_required
def empleado_view(RUT):
    if current_user.id != RUT and not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    cursor = db.cursor(dictionary=True)
    query = "SELECT * FROM asistencias WHERE RUT = %s"
    cursor.execute(query, (RUT,))
    registros = cursor.fetchall()
    cursor.close()
    return render_template('empleado.html', registros=registros)

# RUTA PARA ELIMINAR UN REGISTRO
@app.route('/eliminar_registro/<int:id_asistencia>')
@login_required
def eliminar_registro(id_asistencia):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    cursor = db.cursor()
    sql = "DELETE FROM asistencias WHERE id_asistencia = %s"
    cursor.execute(sql, (id_asistencia,))
    db.commit()
    cursor.close()
    return redirect(url_for('admin_view'))

# VISTA PARA REGISTRAR ASISTENCIA (ADMIN)
@app.route('/registro_asistencia', methods=['GET', 'POST'])
@login_required
def registro_asistencia():
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    if request.method == 'POST':
        RUT = request.form['RUT']
        fecha = request.form['fecha']
        estado = request.form['estado']
        hora_entrada = request.form.get('hora_entrada')
        hora_salida = request.form.get('hora_salida')
        
        if not hora_entrada:
            hora_entrada = None
        if not hora_salida:
            hora_salida = None

        cursor = db.cursor()
        sql = "INSERT INTO asistencias (RUT, fecha, estado, hora_entrada, hora_salida) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(sql, (RUT, fecha, estado, hora_entrada, hora_salida))
        db.commit()
        cursor.close()
        return redirect(url_for('admin_view'))
    
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios")
    empleados = cursor.fetchall()
    cursor.close()
    return render_template('registro_asistencia.html', empleados=empleados)

# RUTA PARA EL CALENDARIO
@app.route('/calendario/<int:anio>/<int:mes>')
@login_required
def ver_calendario(anio, mes):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403

    mes_numero = mes
    nombre_mes = NOMBRES_MESES[mes - 1]
    
    # Obtener el último día del mes
    num_dias = calendar.monthrange(anio, mes)[1]
    dias_mes = list(range(1, num_dias + 1))
    
    # Obtener todos los empleados y sus asistencias para el mes seleccionado
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT RUT, nombre_completo, servicio FROM usuarios")
    empleados_db = cursor.fetchall()

    calendario = {}
    for empleado in empleados_db:
        empleado['asistencias'] = {}
        calendario[empleado['RUT']] = empleado

    # Obtener asistencias del mes
    cursor.execute(
        "SELECT RUT, DAY(fecha) as dia, estado, id_asistencia FROM asistencias WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s",
        (anio, mes)
    )
    asistencias_db = cursor.fetchall()
    cursor.close()

    for asistencia in asistencias_db:
        rut = asistencia['RUT']
        dia = asistencia['dia']
        if rut in calendario:
            calendario[rut]['asistencias'][dia] = {
                'estado': asistencia['estado'],
                'id_asistencia': asistencia['id_asistencia']
            }

    return render_template(
        'ver_calendario.html',
        calendario=calendario,
        dias=dias_mes,
        mes=nombre_mes,
        anio=anio,
        mes_numero=mes_numero
    )

# RUTA PARA SELECCIONAR MES Y AÑO (CORREGIDA)
@app.route('/seleccionar_mes', methods=['GET', 'POST'])
@login_required
def seleccionar_mes():
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    anio_actual = date.today().year
    meses_info = [
        {'numero': i + 1, 'nombre': NOMBRES_MESES[i]} for i in range(12)
    ]
    return render_template('seleccionar_mes.html', anio_actual=anio_actual, meses=meses_info)


# RUTA PARA REGISTRAR ASISTENCIA DESDE EL CALENDARIO
@app.route('/registro_asistencia_calendario/<string:RUT>/<int:dia>/<int:mes>/<int:anio>', methods=['GET', 'POST'])
@login_required
def registro_asistencia_calendario(RUT, dia, mes, anio):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403

    fecha = date(anio, mes, dia)
    
    if request.method == 'POST':
        estado = request.form['estado']
        hora_entrada = request.form.get('hora_entrada')
        hora_salida = request.form.get('hora_salida')
        
        if not hora_entrada:
            hora_entrada = None
        if not hora_salida:
            hora_salida = None

        cursor = db.cursor()
        sql = "INSERT INTO asistencias (RUT, fecha, estado, hora_entrada, hora_salida) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(sql, (RUT, fecha, estado, hora_entrada, hora_salida))
        db.commit()
        cursor.close()
        return redirect(url_for('ver_calendario', anio=anio, mes=mes))
    
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE RUT = %s", (RUT,))
    empleado = cursor.fetchone()
    cursor.close()

    nombre_mes = NOMBRES_MESES[mes - 1]
    return render_template(
        'registro_asistencia_calendario.html',
        empleado=empleado,
        dia=dia,
        mes=nombre_mes,
        anio=anio,
        mes_numero=mes
    )

# RUTA PARA EXPORTAR DATOS A EXCEL
@app.route('/exportar_excel')
@login_required
def exportar_excel():
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            u.RUT,
            u.nombre_completo,
            u.servicio,
            a.fecha,
            a.hora_entrada,
            a.hora_salida,
            a.estado
        FROM asistencias a
        JOIN usuarios u ON a.RUT = u.RUT
        ORDER BY a.fecha DESC
    """)
    registros = cursor.fetchall()
    cursor.close()

    df = pd.DataFrame(registros)
    
    # Crea un archivo Excel en memoria
    excel_file = 'reporte_asistencias.xlsx'
    df.to_excel(excel_file, index=False)
    
    return send_file(excel_file, as_attachment=True)

# VISTA PARA EDITAR REGISTROS
@app.route('/editar_asistencia/<int:id_asistencia>', methods=['GET', 'POST'])
@login_required
def editar_asistencia(id_asistencia):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM asistencias WHERE id_asistencia = %s", (id_asistencia,))
    registro = cursor.fetchone()
    
    if request.method == 'POST':
        estado = request.form['estado']
        hora_entrada = request.form.get('hora_entrada')
        hora_salida = request.form.get('hora_salida')
        
        if not hora_entrada:
            hora_entrada = None
        if not hora_salida:
            hora_salida = None

        sql = "UPDATE asistencias SET estado = %s, hora_entrada = %s, hora_salida = %s WHERE id_asistencia = %s"
        cursor.execute(sql, (estado, hora_entrada, hora_salida, id_asistencia))
        db.commit()
        cursor.close()
        return redirect(url_for('admin_view'))
    
    cursor.close()
    return render_template('editar_asistencia.html', registro=registro)


# VISTA PARA ELIMINAR EMPLEADOS
@app.route('/eliminar_empleado/<string:RUT>')
@login_required
def eliminar_empleado(RUT):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403

    cursor = db.cursor()
    # Eliminar registros de asistencia del empleado primero
    sql_asistencias = "DELETE FROM asistencias WHERE RUT = %s"
    cursor.execute(sql_asistencias, (RUT,))
    
    # Eliminar el empleado
    sql_empleado = "DELETE FROM usuarios WHERE RUT = %s"
    cursor.execute(sql_empleado, (RUT,))
    
    db.commit()
    cursor.close()
    return redirect(url_for('admin_view'))


# VISTA PARA AGREGAR NUEVOS EMPLEADOS
@app.route('/agregar_empleado', methods=['GET', 'POST'])
@login_required
def agregar_empleado():
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    if request.method == 'POST':
        RUT = request.form['RUT']
        nombre_completo = request.form['nombre_completo']
        email = request.form['email']
        contraseña = request.form['contraseña']
        rol = request.form['rol']
        servicio = request.form['servicio']
        
        cursor = db.cursor()
        sql = "INSERT INTO usuarios (RUT, nombre_completo, email, contraseña, rol, servicio) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.execute(sql, (RUT, nombre_completo, email, contraseña, rol, servicio))
        db.commit()
        cursor.close()
        return redirect(url_for('admin_view'))

    return render_template('agregar_empleado.html')

# VISTA PARA EDITAR EMPLEADOS
@app.route('/editar_empleado/<string:RUT>', methods=['GET', 'POST'])
@login_required
def editar_empleado(RUT):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE RUT = %s", (RUT,))
    empleado = cursor.fetchone()
    
    if request.method == 'POST':
        nombre_completo = request.form['nombre_completo']
        email = request.form['email']
        contraseña = request.form['contraseña']
        rol = request.form['rol']
        servicio = request.form['servicio']
        
        sql = "UPDATE usuarios SET nombre_completo = %s, email = %s, contraseña = %s, rol = %s, servicio = %s WHERE RUT = %s"
        cursor.execute(sql, (nombre_completo, email, contraseña, rol, servicio, RUT))
        db.commit()
        cursor.close()
        return redirect(url_for('admin_view'))

    cursor.close()
    return render_template('editar_empleado.html', empleado=empleado)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
