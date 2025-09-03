from flask import Flask, render_template, request, redirect, url_for, session, send_file
import mysql.connector
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
import calendar
from datetime import date

# Inicializar la aplicación de Flask
app = Flask(__name__)
app.secret_key = 'JustTheWayYouAre.1996' # ¡IMPORTANTE! Cámbialo por una clave segura

# Configurar la conexión a la base de datos MySQL
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="JustTheWayYouAre.1996", # ¡IMPORTANTE! Reemplaza esto con tu contraseña
    database="empresa_asistencias"
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

# RUTA PARA EDITAR UN REGISTRO (Muestra el formulario)
@app.route('/editar_registro/<int:id_asistencia>')
@login_required
def editar_registro(id_asistencia):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT u.nombre_completo, a.* FROM asistencias a JOIN usuarios u ON a.RUT = u.RUT WHERE a.id_asistencia = %s", (id_asistencia,))
    registro_a_editar = cursor.fetchone()
    cursor.close()
    
    if not registro_a_editar:
        return "Registro no encontrado", 404

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT RUT, nombre_completo FROM usuarios WHERE rol = 'empleado' OR rol LIKE '%administrador%'")
    empleados = cursor.fetchall()
    cursor.close()

    return render_template('editar_registro.html', registro=registro_a_editar, empleados=empleados)

# RUTA PARA PROCESAR LA EDICIÓN DEL REGISTRO
@app.route('/actualizar_registro/<int:id_asistencia>', methods=['POST'])
@login_required
def actualizar_registro(id_asistencia):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    RUT = request.form['RUT']
    fecha = request.form['fecha']
    hora_entrada = request.form.get('hora_entrada', None)
    hora_salida = request.form.get('hora_salida', None)
    estado = request.form['estado']

    cursor = db.cursor()
    sql = "UPDATE asistencias SET RUT = %s, fecha = %s, hora_entrada = %s, hora_salida = %s, estado = %s WHERE id_asistencia = %s"
    values = (RUT, fecha, hora_entrada, hora_salida, estado, id_asistencia)
    cursor.execute(sql, values)
    db.commit()
    cursor.close()
    return redirect(url_for('admin_view'))

# RUTA PARA EXPORTAR DATOS A UN ARCHIVO CSV/EXCEL
@app.route('/exportar')
@login_required
def exportar_registros():
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT u.nombre_completo, a.fecha, a.hora_entrada, a.hora_salida, a.estado FROM asistencias a JOIN usuarios u ON a.RUT = u.RUT")
    registros = cursor.fetchall()
    cursor.close()

    df = pd.DataFrame(registros)
    
    output = pd.ExcelWriter('asistencias.xlsx', engine='xlsxwriter')
    df.to_excel(output, sheet_name='Registros', index=False)
    output.close()

    return send_file('asistencias.xlsx', as_attachment=True)

# RUTA PARA MOSTRAR EL SELECTOR DE MES
@app.route('/seleccionar_mes', methods=['GET', 'POST'])
@login_required
def seleccionar_mes():
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    if request.method == 'POST':
        mes = request.form['mes']
        anio = request.form['anio']
        return redirect(url_for('ver_calendario', mes=mes, anio=anio))
        
    return render_template('seleccionar_mes.html')

# RUTA PARA VER EL CALENDARIO MENSUAL
@app.route('/ver_calendario/<int:anio>/<int:mes>')
@login_required
def ver_calendario(anio, mes):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    # Obtener la lista de empleados y administradores con rol de empleado, ordenados por servicio
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT RUT, nombre_completo, servicio FROM usuarios 
        WHERE rol = 'empleado' OR rol LIKE '%administrador%'
        ORDER BY
            CASE servicio
                WHEN 'Bloqueo' THEN 1
                WHEN 'Ingreso' THEN 2
                WHEN 'Mesa Central' THEN 3
                WHEN 'HLF' THEN 4
                ELSE 5 
            END,
            nombre_completo ASC
    """)
    empleados = cursor.fetchall()

    # Obtener los registros de asistencia para el mes y año seleccionados
    query = "SELECT * FROM asistencias WHERE MONTH(fecha) = %s AND YEAR(fecha) = %s"
    cursor.execute(query, (mes, anio))
    asistencias_mes = cursor.fetchall()
    cursor.close()

    # Organizar los datos para la vista de calendario
    calendario_data = {}
    for empleado in empleados:
        calendario_data[empleado['RUT']] = {
            'nombre_completo': empleado['nombre_completo'],
            'servicio': empleado['servicio'],
            'asistencias': {}
        }

    for asistencia in asistencias_mes:
        dia = asistencia['fecha'].day
        RUT = asistencia['RUT']
        if RUT in calendario_data:
            calendario_data[RUT]['asistencias'][dia] = asistencia

    # Generar la lista de días del mes
    num_dias = calendar.monthrange(anio, mes)[1]
    dias_del_mes = list(range(1, num_dias + 1))
    
    nombre_mes = NOMBRES_MESES[mes - 1]
    
    return render_template('ver_calendario.html',
                           anio=anio,
                           mes=nombre_mes,
                           mes_numero=mes, # <-- Corregido: se pasa el número del mes
                           dias=dias_del_mes,
                           calendario=calendario_data)

# RUTA PARA REGISTRAR ASISTENCIA DESDE EL CALENDARIO
@app.route('/registrar_asistencia_calendario/<string:RUT>/<int:dia>/<int:mes>/<int:anio>')
@login_required
def registrar_asistencia_calendario(RUT, dia, mes, anio):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403

    # Obtener los datos del empleado
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT RUT, nombre_completo, servicio FROM usuarios WHERE RUT = %s", (RUT,))
    empleado = cursor.fetchone()
    cursor.close()

    if not empleado:
        return "Empleado no encontrado", 404

    fecha_registro = date(anio, mes, dia)
    fecha_formato = fecha_registro.strftime('%d-%m-%Y')
    
    return render_template('registro_asistencia_calendario.html', 
                           empleado=empleado, 
                           fecha=fecha_formato,
                           fecha_iso=fecha_registro.isoformat())

# RUTA PARA GUARDAR ASISTENCIA DESDE EL CALENDARIO
@app.route('/guardar_asistencia_calendario', methods=['POST'])
@login_required
def guardar_asistencia_calendario():
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    RUT = request.form['RUT']
    fecha = request.form['fecha']
    hora_entrada = request.form.get('hora_entrada', None)
    hora_salida = request.form.get('hora_salida', None)
    estado = request.form['estado']

    cursor = db.cursor()
    sql = "INSERT INTO asistencias (RUT, fecha, hora_entrada, hora_salida, estado) VALUES (%s, %s, %s, %s, %s)"
    values = (RUT, fecha, hora_entrada, hora_salida, estado)
    cursor.execute(sql, values)
    db.commit()
    cursor.close()

    # Redirigir de vuelta al calendario
    fecha_obj = date.fromisoformat(fecha)
    return redirect(url_for('ver_calendario', mes=fecha_obj.month, anio=fecha_obj.year))

# RUTA PARA EDITAR ASISTENCIA DESDE EL CALENDARIO
@app.route('/editar_asistencia_calendario/<int:id_asistencia>')
@login_required
def editar_asistencia_calendario(id_asistencia):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT u.nombre_completo, u.servicio, a.* FROM asistencias a JOIN usuarios u ON a.RUT = u.RUT WHERE a.id_asistencia = %s", (id_asistencia,))
    registro = cursor.fetchone()
    cursor.close()

    if not registro:
        return "Registro no encontrado", 404
        
    return render_template('editar_asistencia_calendario.html', registro=registro)

# RUTA PARA ACTUALIZAR ASISTENCIA DESDE EL CALENDARIO
@app.route('/actualizar_asistencia_calendario/<int:id_asistencia>', methods=['POST'])
@login_required
def actualizar_asistencia_calendario(id_asistencia):
    if not current_user.tiene_rol('administrador'):
        return "Acceso denegado", 403
    
    hora_entrada = request.form.get('hora_entrada', None)
    hora_salida = request.form.get('hora_salida', None)
    estado = request.form['estado']

    cursor = db.cursor(dictionary=True)
    cursor.execute("UPDATE asistencias SET hora_entrada = %s, hora_salida = %s, estado = %s WHERE id_asistencia = %s", (hora_entrada, hora_salida, estado, id_asistencia))
    db.commit()
    
    cursor.execute("SELECT fecha FROM asistencias WHERE id_asistencia = %s", (id_asistencia,))
    fecha_obj = cursor.fetchone()['fecha']
    cursor.close()
    
    return redirect(url_for('ver_calendario', mes=fecha_obj.month, anio=fecha_obj.year))


if __name__ == '__main__':
    app.run(debug=True)