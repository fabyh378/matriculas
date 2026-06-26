from flask import Flask, render_template, request, redirect, flash, session, send_file
import os
from dotenv import load_dotenv
import sqlite3
import psycopg2
import re
from datetime import datetime
import io
import csv
import smtplib
import ssl
from email.message import EmailMessage
import pyotp
import urllib.parse
from waitress import serve
from pyngrok import ngrok
import logging
import secrets
from werkzeug.security import check_password_hash, generate_password_hash
from markupsafe import Markup

load_dotenv()

app = Flask(__name__, static_folder='static')

# Configuración de logging
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# SMTP configuration: update with your mail provider settings
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', 'tucorreo@example.com')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', 'tu_contraseña')
EMAIL_SENDER = os.getenv('EMAIL_SENDER', 'no-reply@tuinstitucion.cl')
ESTABLECIMIENTO = os.getenv('ESTABLECIMIENTO', 'Liceo Claudina Urrutia de Lavín')
CODIGO_ESTABLECIMIENTO = os.getenv('CODIGO_ESTABLECIMIENTO', '0000')

# Flask secret key
app.secret_key = os.getenv('SECRET_KEY', 'empresa_123')

DATABASE_URL = os.getenv('DATABASE_URL')

class PostgreSQLCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, query, vars=None):
        query = query.replace('?', '%s')
        if 'INSERT OR IGNORE INTO' in query:
            # Reemplazar por INSERT INTO ... ON CONFLICT DO NOTHING
            query = query.replace('INSERT OR IGNORE INTO', 'INSERT INTO')
            query += ' ON CONFLICT DO NOTHING'
        return self.cursor.execute(query, vars)

    def executemany(self, query, vars_list):
        query = query.replace('?', '%s')
        if 'INSERT OR IGNORE INTO' in query:
            query = query.replace('INSERT OR IGNORE INTO', 'INSERT INTO')
            query += ' ON CONFLICT DO NOTHING'
        return self.cursor.executemany(query, vars_list)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()

    @property
    def description(self):
        return self.cursor.description

class PostgreSQLConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return PostgreSQLCursorWrapper(self.conn.cursor())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

DB = "database.db"

def get_db():
    import sys
    if DATABASE_URL and not app.config.get('TESTING') and 'pytest' not in sys.modules:
        conn = psycopg2.connect(DATABASE_URL)
        return PostgreSQLConnectionWrapper(conn)
    else:
        conn = sqlite3.connect(DB)
        return conn


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored_password, provided_password):
    if not stored_password or not provided_password:
        return False
    try:
        if check_password_hash(stored_password, provided_password):
            return True
    except ValueError:
        pass
    return False


def password_is_hashed(password):
    return isinstance(password, str) and password.startswith('pbkdf2:')


def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']

@app.context_processor
def inject_csrf_token():
    return {
        'csrf_token': generate_csrf_token(),
        'csrf_field': lambda: Markup(f'<input type="hidden" name="_csrf_token" value="{session.get("_csrf_token", "")}">')
    }

@app.before_request
def csrf_protect():
    if request.method == 'POST':
        token = request.form.get('_csrf_token') or request.headers.get('X-CSRFToken') or request.headers.get('X-CSRF-Token')
        if not token or token != session.get('_csrf_token'):
            flash('Token CSRF inválido. Intenta de nuevo.')
            return redirect(request.referrer or '/')

def init_db():
    try:
        conn = get_db()
        cursor = conn.cursor()

        if DATABASE_URL:
            # PostgreSQL Table Creation (all columns pre-defined, no PRAGMA/ALTER needed)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE,
                    password TEXT,
                    rol VARCHAR(50),
                    nombre_completo TEXT,
                    asignatura TEXT,
                    twofa_secret TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS matriculas (
                    id SERIAL PRIMARY KEY,
                    alumno_nombre TEXT,
                    alumno_rut VARCHAR(50),
                    alumno_direccion TEXT,
                    alumno_telefono VARCHAR(50),
                    apoderado_nombre TEXT,
                    apoderado_rut VARCHAR(50),
                    apoderado_telefono VARCHAR(50),
                    apoderado_email TEXT,
                    apoderado_direccion TEXT,
                    suplente_nombre TEXT,
                    suplente_rut VARCHAR(50),
                    suplente_telefono VARCHAR(50),
                    suplente_direccion TEXT,
                    ano_escolar VARCHAR(50),
                    grado VARCHAR(50),
                    seccion VARCHAR(50),
                    jornada VARCHAR(50),
                    fecha_nacimiento VARCHAR(50),
                    tipo_matricula VARCHAR(50),
                    estado_matricula VARCHAR(50),
                    fecha_matricula VARCHAR(50),
                    establecimiento TEXT,
                    codigo_utp VARCHAR(50),
                    sector VARCHAR(50),
                    jornada_completa VARCHAR(50),
                    sae_asignacion VARCHAR(50),
                    certificado_nacimiento VARCHAR(50),
                    situacion_academica TEXT,
                    apoderado_poder_simple VARCHAR(50)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS asistencia (
                    id SERIAL PRIMARY KEY,
                    alumno_nombre TEXT,
                    alumno_rut VARCHAR(50),
                    fecha VARCHAR(50),
                    presente INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS permisos_solicitados (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    permiso VARCHAR(100),
                    descripcion TEXT,
                    estado VARCHAR(50) DEFAULT 'pendiente',
                    fecha_solicitud VARCHAR(50),
                    fecha_respuesta VARCHAR(50)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_mensajes (
                    id SERIAL PRIMARY KEY,
                    solicitud_id INTEGER,
                    user_id INTEGER,
                    mensaje TEXT,
                    fecha VARCHAR(50)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS apoderados (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    alumno_rut VARCHAR(50),
                    relacion VARCHAR(50)
                )
            ''')
            cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_apoderados_user_alumno ON apoderados (user_id, alumno_rut)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS solicitudes_informes (
                    id SERIAL PRIMARY KEY,
                    apoderado_id INTEGER,
                    alumno_rut VARCHAR(50),
                    tipo_informe VARCHAR(100),
                    descripcion TEXT,
                    estado VARCHAR(50) DEFAULT 'pendiente',
                    fecha_solicitud VARCHAR(50),
                    fecha_respuesta VARCHAR(50),
                    administrativo_id INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_informes_mensajes (
                    id SERIAL PRIMARY KEY,
                    solicitud_id INTEGER,
                    user_id INTEGER,
                    mensaje TEXT,
                    fecha VARCHAR(50)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS calificaciones (
                    id SERIAL PRIMARY KEY,
                    alumno_rut VARCHAR(50),
                    asignatura VARCHAR(100),
                    docente_id INTEGER,
                    nota REAL,
                    fecha VARCHAR(50),
                    comentario TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS horarios (
                    id SERIAL PRIMARY KEY,
                    asignatura VARCHAR(100),
                    docente_id INTEGER,
                    dia_semana VARCHAR(50),
                    hora_inicio VARCHAR(50),
                    hora_fin VARCHAR(50),
                    aula VARCHAR(50)
                )
            ''')
        else:
            # SQLite Table Creation
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    rol TEXT,
                    nombre_completo TEXT,
                    asignatura TEXT,
                    twofa_secret TEXT
                )
            ''')
            cursor.execute("PRAGMA table_info(users)")
            user_columns = [row[1] for row in cursor.fetchall()]
            if 'asignatura' not in user_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN asignatura TEXT')
                user_columns.append('asignatura')
            if 'twofa_secret' not in user_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN twofa_secret TEXT')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS matriculas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alumno_nombre TEXT,
                    alumno_rut TEXT,
                    alumno_direccion TEXT,
                    alumno_telefono TEXT,
                    apoderado_nombre TEXT,
                    apoderado_rut TEXT,
                    apoderado_telefono TEXT,
                    apoderado_email TEXT,
                    apoderado_direccion TEXT,
                    suplente_nombre TEXT,
                    suplente_rut TEXT,
                    suplente_telefono TEXT,
                    suplente_direccion TEXT,
                    ano_escolar TEXT,
                    grado TEXT,
                    seccion TEXT,
                    jornada TEXT,
                    fecha_nacimiento TEXT,
                    tipo_matricula TEXT,
                    estado_matricula TEXT,
                    fecha_matricula TEXT,
                    establecimiento TEXT,
                    codigo_utp TEXT,
                    sector TEXT,
                    jornada_completa TEXT,
                    sae_asignacion TEXT,
                    certificado_nacimiento TEXT,
                    situacion_academica TEXT,
                    apoderado_poder_simple TEXT
                )
            ''')
            cursor.execute("PRAGMA table_info(matriculas)")
            matricula_columns = [row[1] for row in cursor.fetchall()]
            missing_columns = [
                ('grado', 'TEXT'),
                ('seccion', 'TEXT'),
                ('jornada', 'TEXT'),
                ('fecha_nacimiento', 'TEXT'),
                ('tipo_matricula', 'TEXT'),
                ('estado_matricula', 'TEXT'),
                ('fecha_matricula', 'TEXT'),
                ('establecimiento', 'TEXT'),
                ('codigo_utp', 'TEXT'),
                ('sector', 'TEXT'),
                ('jornada_completa', 'TEXT'),
                ('sae_asignacion', 'TEXT'),
                ('certificado_nacimiento', 'TEXT'),
                ('situacion_academica', 'TEXT'),
                ('apoderado_poder_simple', 'TEXT')
            ]
            for column_name, column_type in missing_columns:
                if column_name not in matricula_columns:
                    cursor.execute(f'ALTER TABLE matriculas ADD COLUMN {column_name} {column_type}')
                    matricula_columns.append(column_name)

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS asistencia (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alumno_nombre TEXT,
                    alumno_rut TEXT,
                    fecha TEXT,
                    presente INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS permisos_solicitados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    permiso TEXT,
                    descripcion TEXT,
                    estado TEXT DEFAULT 'pendiente',
                    fecha_solicitud TEXT,
                    fecha_respuesta TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_mensajes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    solicitud_id INTEGER,
                    user_id INTEGER,
                    mensaje TEXT,
                    fecha TEXT,
                    FOREIGN KEY(solicitud_id) REFERENCES permisos_solicitados(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS apoderados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    alumno_rut TEXT,
                    relacion TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_apoderados_user_alumno ON apoderados (user_id, alumno_rut)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS solicitudes_informes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    apoderado_id INTEGER,
                    alumno_rut TEXT,
                    tipo_informe TEXT,
                    descripcion TEXT,
                    estado TEXT DEFAULT 'pendiente',
                    fecha_solicitud TEXT,
                    fecha_respuesta TEXT,
                    administrativo_id INTEGER,
                    FOREIGN KEY(apoderado_id) REFERENCES users(id),
                    FOREIGN KEY(administrativo_id) REFERENCES users(id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_informes_mensajes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    solicitud_id INTEGER,
                    user_id INTEGER,
                    mensaje TEXT,
                    fecha TEXT,
                    FOREIGN KEY(solicitud_id) REFERENCES solicitudes_informes(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS calificaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alumno_rut TEXT,
                    asignatura TEXT,
                    docente_id INTEGER,
                    nota REAL,
                    fecha TEXT,
                    comentario TEXT,
                    FOREIGN KEY(docente_id) REFERENCES users(id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS horarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asignatura TEXT,
                    docente_id INTEGER,
                    dia_semana TEXT,
                    hora_inicio TEXT,
                    hora_fin TEXT,
                    aula TEXT,
                    FOREIGN KEY(docente_id) REFERENCES users(id)
                )
            ''')

        # Insertar usuarios por defecto
        cursor.execute("INSERT OR IGNORE INTO users (id, username, password, rol, nombre_completo, asignatura) VALUES (1, 'admin', ?, 'admin', 'Administrador', NULL)", (hash_password('admin123'),))
        cursor.execute("INSERT OR IGNORE INTO users (username, password, rol, nombre_completo, asignatura) VALUES ('administrativo', ?, 'administrativo', 'Personal Administrativo', NULL)", (hash_password('admin123'),))
        cursor.execute("INSERT OR IGNORE INTO users (username, password, rol, nombre_completo, asignatura) VALUES ('docente', ?, 'docente', 'Profesor Juan Pérez', 'Lenguaje')", (hash_password('admin123'),))
        cursor.execute("INSERT OR IGNORE INTO users (username, password, rol, nombre_completo, asignatura) VALUES ('apoderado1', ?, 'apoderado', 'María García López', NULL)", (hash_password('admin123'),))

        subjects = ['Lenguaje', 'Historia', 'Matematica', 'Educacion Fisica', 'Arte', 'Ingles', 'Musica', 'Ciencias Naturales', 'Quimica']
        for i in range(1, 51):
            username = f'docente{i}'
            nombre = f'Profesora {i}' if i % 2 == 0 else f'Profesor {i}'
            asignatura = subjects[(i - 1) % len(subjects)]
            cursor.execute(
                "INSERT OR IGNORE INTO users (username, password, rol, nombre_completo, asignatura) VALUES (?, ?, 'docente', ?, ?)",
                (username, hash_password('docente123'), nombre, asignatura)
            )
        conn.commit()
        conn.close()
        print("[OK] Base de datos inicializada correctamente")
    except Exception as e:
        print(f"[ERROR] Inicializando la base de datos: {e}")

# Inicializar la base de datos al arrancar la aplicación
with app.app_context():
    init_db()

def normalizar_identificador(value):
    if not value:
        return ''
    return re.sub(r'[\.\s]', '', value).upper()


def normalizar_rut(rut):
    return normalizar_identificador(rut)


def calcular_digito_verificador(rut_sin_dv):
    try:
        rut_str = str(rut_sin_dv)[::-1]
        multiplicadores = [2, 3, 4, 5, 6, 7]
        suma = 0
        for i, digito in enumerate(rut_str):
            multiplicador = multiplicadores[i % 6]
            suma += int(digito) * multiplicador
        resto = suma % 11
        diferencia = 11 - resto
        if diferencia == 11:
            return '0'
        elif diferencia == 10:
            return 'K'
        else:
            return str(diferencia)
    except Exception:
        return None


def validar_rut_chileno(rut):
    parts = rut.split('-')
    if len(parts) != 2:
        return False
    cuerpo, dv = parts
    if not cuerpo.isdigit():
        return False
    dv_calculado = calcular_digito_verificador(cuerpo)
    return dv.upper() == dv_calculado


def validar_identificador_sige(value):
    if not value:
        return False

    cleaned = normalizar_identificador(value)

    # Validar RUT chileno estándar
    if re.match(r'^\d{7,8}-[0-9K]$', cleaned):
        return validar_rut_chileno(cleaned)

    # Validar identificadores provisorios IPA/IPE para estudiantes o apoderados extranjeros
    if re.match(r'^(IPA|IPE)\d{4,10}$', cleaned):
        return True

    return False


def validar_rut(rut):
    return validar_identificador_sige(rut)


def is_valid_email(email):
    if not email:
        return False
    return re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email) is not None


def get_apoderado_ruts(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT alumno_rut FROM apoderados WHERE user_id = ?', (user_id,))
    ruts = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ruts


def asociar_matriculas_apoderado(user_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT username, nombre_completo FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return

        username, nombre_completo = user
        username_norm = username.strip().lower() if username else ''
        nombre_norm = nombre_completo.strip().lower() if nombre_completo else ''

        conditions = []
        params = []
        if nombre_norm:
            conditions.append('LOWER(apoderado_nombre) = ?')
            params.append(nombre_norm)
        if username_norm and username_norm != nombre_norm:
            conditions.append('LOWER(apoderado_nombre) = ?')
            params.append(username_norm)

        if not conditions:
            conn.close()
            return

        query = 'SELECT DISTINCT alumno_rut FROM matriculas WHERE ' + ' OR '.join(conditions)
        cursor.execute(query, params)
        alumno_ruts = [row[0] for row in cursor.fetchall()]

        for alumno_rut in alumno_ruts:
            cursor.execute(
                'INSERT OR IGNORE INTO apoderados (user_id, alumno_rut, relacion) VALUES (?, ?, ?)',
                (user_id, alumno_rut, 'titular')
            )

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error en asociar_matriculas_apoderado para user_id {user_id}: {str(e)}")
        # No relanzar la excepción para no interrumpir el flujo


def send_email_to_apoderado(email_address, apoderado_nombre, alumno_nombre, alumno_rut):
    try:
        if not is_valid_email(email_address):
            return False

        message = EmailMessage()
        message['Subject'] = 'Confirmación de Matrícula'
        message['From'] = EMAIL_SENDER
        message['To'] = email_address
        message.set_content(f"Hola {apoderado_nombre},\n\nLa matrícula del alumno {alumno_nombre} (RUT: {alumno_rut}) ha sido registrada correctamente en el sistema.\n\nSi no solicitaste esta acción, por favor contacta a la institución.\n\nSaludos,\nEquipo de administración.")

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)

        return True
    except Exception as e:
        logger.error(f"Error enviando correo a {email_address}: {e}")
        return False

@app.route('/login', methods=['GET', 'POST'])
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password, rol, nombre_completo, asignatura, twofa_secret FROM users WHERE username=?", (user,))
        data = cursor.fetchone()

        if data:
            user_id, username, stored_password, user_rol, nombre_completo, asignatura, twofa_secret = data
            if verify_password(stored_password, pwd):
                if not password_is_hashed(stored_password):
                    cursor.execute('UPDATE users SET password = ? WHERE id = ?', (hash_password(pwd), user_id))
                    conn.commit()

                if user_rol == 'admin' and twofa_secret:
                    session['pending_2fa_user_id'] = user_id
                    session['pending_2fa_username'] = username
                    session['pending_2fa_rol'] = user_rol
                    session['pending_2fa_nombre'] = nombre_completo
                    session['pending_2fa_asignatura'] = asignatura
                    session['pending_2fa_secret'] = twofa_secret
                    conn.close()
                    return redirect('/twofa')

                session['user'] = username
                session['usuario'] = username
                session['user_id'] = user_id
                session['rol'] = user_rol
                session['nombre'] = nombre_completo
                session['asignatura'] = asignatura
                
                logger.info(f"Usuario {username} ({user_rol}) inició sesión exitosamente")
                conn.close()
                
                if user_rol == 'admin':
                    return redirect('/dashboard')
                elif user_rol == 'administrativo':
                    return redirect('/dashboard_admin')
                elif user_rol == 'docente':
                    return redirect('/dashboard_docente')
                elif user_rol == 'apoderado':
                    return redirect('/dashboard_apoderado')
            else:
                conn.close()
                flash("Credenciales incorrectas")
        else:
            conn.close()
            flash("Credenciales incorrectas")

    return render_template('login.html')

@app.route('/twofa', methods=['GET', 'POST'])
def twofa():
    if 'pending_2fa_user_id' not in session:
        return redirect('/')

    if session.get('pending_2fa_rol') != 'admin':
        session.pop('pending_2fa_user_id', None)
        session.pop('pending_2fa_username', None)
        session.pop('pending_2fa_rol', None)
        session.pop('pending_2fa_nombre', None)
        session.pop('pending_2fa_asignatura', None)
        session.pop('pending_2fa_secret', None)
        return redirect('/')

    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        secret = session.get('pending_2fa_secret')
        if not secret:
            flash('Error de configuración de 2FA. Intenta nuevamente.')
            return redirect('/')

        totp = pyotp.TOTP(secret)
        if totp.verify(token, valid_window=1):
            session['user'] = session.pop('pending_2fa_username')
            session['usuario'] = session.get('user')
            session['user_id'] = session.pop('pending_2fa_user_id')
            session['rol'] = session.pop('pending_2fa_rol')
            session['nombre'] = session.pop('pending_2fa_nombre')
            session['asignatura'] = session.pop('pending_2fa_asignatura')
            session.pop('pending_2fa_secret', None)

            if session['rol'] == 'admin':
                return redirect('/dashboard')
            elif session['rol'] == 'administrativo':
                return redirect('/dashboard_admin')
            elif session['rol'] == 'docente':
                return redirect('/dashboard_docente')
            elif session['rol'] == 'apoderado':
                return redirect('/dashboard_apoderado')

        flash('Código de autenticación inválido. Por favor revisa tu aplicación autenticadora e intenta de nuevo.')

    return render_template('twofa.html')


@app.route('/reset_2fa', methods=['POST'])
def reset_2fa():
    if 'user' not in session or session.get('rol') != 'admin':
        flash('Solo el administrador puede resetear 2FA.')
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET twofa_secret=NULL WHERE username=?', (session['user'],))
    conn.commit()
    conn.close()
    
    flash('La autenticación de dos pasos ha sido desactivada. Puedes configurarla nuevamente desde el menú.')
    return redirect('/dashboard')

@app.route('/setup_2fa', methods=['GET', 'POST'])
def setup_2fa():
    if 'user' not in session or session.get('rol') != 'admin':
        flash('Solo el administrador puede configurar 2FA.')
        return redirect('/')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT twofa_secret FROM users WHERE username=?', (session['user'],))
    row = cursor.fetchone()
    secret = row[0] if row else None

    if request.method == 'POST' or not secret:
        secret = pyotp.random_base32(32)
        cursor.execute('UPDATE users SET twofa_secret=? WHERE username=?', (secret, session['user']))
        conn.commit()
        flash('La autenticación de dos pasos se ha configurado. Escanea el código QR con tu aplicación autenticadora.')

    conn.close()

    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=session['user'], issuer_name='Sistema Matricula')
    qr_uri = urllib.parse.quote(provisioning_uri, safe='')
    grouped_secret = ' '.join(secret[i:i+4] for i in range(0, len(secret), 4))
    return render_template('setup_2fa.html', secret=grouped_secret, uri=provisioning_uri, qr_uri=qr_uri)

@app.route('/home')
def home():
    if 'user' not in session:
        return redirect('/')
    
    rol = session.get('rol')
    if rol == 'admin':
        return redirect('/dashboard')
    elif rol == 'administrativo':
        return redirect('/dashboard_admin')
    elif rol == 'docente':
        return redirect('/dashboard_docente')
    elif rol == 'apoderado':
        return redirect('/dashboard_apoderado')
    
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session or session.get('rol') != 'admin':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM matriculas")
    total_matriculas = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users")
    total_usuarios = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM asistencia")
    total_asistencias = cursor.fetchone()[0]
    conn.close()
    
    return render_template('dashboard_admin.html', total_matriculas=total_matriculas, total_usuarios=total_usuarios, total_asistencias=total_asistencias)

@app.route('/dashboard_admin')
def dashboard_admin():
    if 'user' not in session or session.get('rol') != 'administrativo':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM matriculas")
    total_matriculas = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM asistencia WHERE presente=1")
    presentes_hoy = cursor.fetchone()[0]
    conn.close()
    
    return render_template('dashboard_administrativo.html', total_matriculas=total_matriculas, presentes_hoy=presentes_hoy)

@app.route('/descargar_asistencia_excel')
def descargar_asistencia_excel():
    if 'user' not in session or session.get('rol') not in ['admin', 'administrativo', 'docente']:
        return redirect('/')
    
    # Obtener la fecha actual
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener asistencia del día actual
    cursor.execute('''
        SELECT alumno_nombre, alumno_rut, fecha, presente 
        FROM asistencia 
        WHERE fecha = ?
        ORDER BY alumno_nombre
    ''', (fecha_hoy,))
    
    asistencias = cursor.fetchall()
    conn.close()
    
    # Crear archivo CSV en memoria
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Escribir encabezados
    writer.writerow(['Nombre del Alumno', 'RUT', 'Fecha', 'Estado'])
    
    # Escribir datos
    for asistencia in asistencias:
        alumno_nombre, alumno_rut, fecha, presente = asistencia
        estado = 'Presente' if presente else 'Ausente'
        writer.writerow([alumno_nombre, alumno_rut, fecha, estado])
    
    # Preparar respuesta
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'asistencia_{fecha_hoy}.csv'
    )

@app.route('/dashboard_docente')
def dashboard_docente():
    if 'user' not in session or session.get('rol') != 'docente':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener total de alumnos
    cursor.execute("SELECT COUNT(*) FROM matriculas")
    total_alumnos = cursor.fetchone()[0]
    
    # Obtener asistencia de hoy
    from datetime import datetime
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM asistencia WHERE fecha=? AND presente=1", (fecha_hoy,))
    presentes_hoy = cursor.fetchone()[0]
    
    # Obtener clases asignadas (por ahora todos los alumnos)
    cursor.execute("SELECT COUNT(*) FROM matriculas")
    alumnos_clase = cursor.fetchone()[0]
    
    conn.close()
    
    return render_template('dashboard_docente.html', 
                         total_alumnos=total_alumnos, 
                         presentes_hoy=presentes_hoy,
                         alumnos_clase=alumnos_clase)

@app.route('/dashboard_apoderado')
def dashboard_apoderado():
    if 'user' not in session or session.get('rol') != 'apoderado':
        return redirect('/')
    
    user_id = session.get('user_id')
    
    asociar_matriculas_apoderado(user_id)

    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener alumno(s) asociado(s) al apoderado
    cursor.execute('''
        SELECT m.alumno_nombre, m.alumno_rut FROM matriculas m
        JOIN apoderados a ON m.alumno_rut = a.alumno_rut
        WHERE a.user_id = ?
    ''', (user_id,))
    
    alumnos = cursor.fetchall()
    
    asistencias = {}
    for alumno_nombre, alumno_rut in alumnos:
        cursor.execute('''
            SELECT COUNT(*) FROM asistencia WHERE alumno_rut=? AND presente=1
        ''', (alumno_rut,))
        presentes = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM asistencia WHERE alumno_rut=? AND presente=0
        ''', (alumno_rut,))
        ausentes = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM asistencia WHERE alumno_rut=?
        ''', (alumno_rut,))
        total = cursor.fetchone()[0]
        
        asistencias[alumno_nombre] = {
            'presentes': presentes,
            'ausentes': ausentes,
            'total': total,
            'porcentaje': round((presentes / total) * 100, 1) if total > 0 else 0
        }
    
    # Obtener solicitudes de informes
    cursor.execute('''
        SELECT si.id, m.alumno_nombre, si.tipo_informe, si.estado, si.fecha_solicitud
        FROM solicitudes_informes si
        LEFT JOIN matriculas m ON si.alumno_rut = m.alumno_rut
        WHERE si.apoderado_id = ?
        ORDER BY si.fecha_solicitud DESC
    ''', (user_id,))
    solicitudes = cursor.fetchall()

    conn.close()
    
    return render_template('dashboard_apoderado.html', alumnos=alumnos, asistencias=asistencias, solicitudes=solicitudes)

@app.route('/nueva_matricula')
def nueva_matricula():
    if 'user' not in session:
        return redirect('/')
    if session.get('rol') not in ['admin', 'administrativo']:
        flash("No tienes permisos para acceder a esta página")
        return redirect('/home')
    return render_template(
        'index.html',
        establecimiento=ESTABLECIMIENTO,
        codigo_utp=CODIGO_ESTABLECIMIENTO,
        fecha_matricula=datetime.now().strftime('%Y-%m-%d')
    )

@app.route('/guardar', methods=['POST'])
def guardar():
    if 'user' not in session:
        return redirect('/')
    
    # Solo admin y administrativo pueden guardar matrículas
    if session.get('rol') not in ['admin', 'administrativo']:
        flash("No tienes permisos para realizar esta acción")
        return redirect('/')

    data = request.form

    alumno_rut = data.get('alumno_rut', '')
    apoderado_rut = data.get('apoderado_rut', '')
    suplente_rut = data.get('suplente_rut', '')
    tipo_matricula = data.get('tipo_matricula', 'Nueva')
    sae_asignacion = data.get('sae_asignacion', '').strip()
    certificado_nacimiento = data.get('certificado_nacimiento', '').strip()
    situacion_academica = data.get('situacion_academica', '').strip()
    apoderado_poder_simple = data.get('apoderado_poder_simple', 'No aplica').strip()

    if not validar_identificador_sige(alumno_rut):
        flash("Identificador del alumno inválido. Ingresa RUT o IPA/IPE.")
        return redirect('/nueva_matricula')

    if not validar_identificador_sige(apoderado_rut):
        flash("Identificador del apoderado inválido. Ingresa RUT o IPA/IPE.")
        return redirect('/nueva_matricula')

    if suplente_rut and not validar_identificador_sige(suplente_rut):
        flash("Identificador del apoderado suplente inválido. Ingresa RUT o IPA/IPE.")
        return redirect('/nueva_matricula')

    if tipo_matricula == 'Nueva' and not sae_asignacion:
        flash("Para matrículas nuevas es obligatorio informar la asignación SAE.")
        return redirect('/nueva_matricula')

    if certificado_nacimiento not in ['Sí', 'No']:
        flash("Debes confirmar si tienes el certificado de nacimiento.")
        return redirect('/nueva_matricula')

    if not situacion_academica:
        flash("Debes ingresar la situación académica del estudiante.")
        return redirect('/nueva_matricula')

    if not data.get('fecha_nacimiento'):
        flash("La fecha de nacimiento del alumno es obligatoria para validar el certificado.")
        return redirect('/nueva_matricula')

    alumno_rut = normalizar_rut(alumno_rut)
    apoderado_rut = normalizar_rut(apoderado_rut)
    suplente_rut = normalizar_rut(suplente_rut)

    try:
        conn = get_db()
        cursor = conn.cursor()

        apoderado_email = data.get('apoderado_email', '').strip()
        if apoderado_email and not is_valid_email(apoderado_email):
            flash("Correo del apoderado inválido")
            return redirect('/nueva_matricula')

        estado_matricula = data.get('estado_matricula', 'Matriculado')
        fecha_matricula = data.get('fecha_matricula', datetime.now().strftime('%Y-%m-%d'))

        cursor.execute('''
            INSERT INTO matriculas (
                alumno_nombre, alumno_rut, alumno_direccion, alumno_telefono,
                apoderado_nombre, apoderado_rut, apoderado_telefono, apoderado_email, apoderado_direccion,
                suplente_nombre, suplente_rut, suplente_telefono, suplente_direccion, ano_escolar,
                grado, seccion, jornada, fecha_nacimiento, tipo_matricula,
                estado_matricula, fecha_matricula, establecimiento, codigo_utp,
                sector, jornada_completa, sae_asignacion, certificado_nacimiento,
                situacion_academica, apoderado_poder_simple
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('alumno_nombre', ''),
            alumno_rut,
            data.get('alumno_direccion', ''),
            data.get('alumno_telefono', ''),
            data.get('apoderado_nombre', ''),
            apoderado_rut,
            data.get('apoderado_telefono', ''),
            apoderado_email,
            data.get('apoderado_direccion', ''),
            data.get('suplente_nombre', ''),
            suplente_rut,
            data.get('suplente_telefono', ''),
            data.get('suplente_direccion', ''),
            data.get('ano_escolar', ''),
            data.get('grado', ''),
            data.get('seccion', ''),
            data.get('jornada', ''),
            data.get('fecha_nacimiento', ''),
            tipo_matricula,
            estado_matricula,
            fecha_matricula,
            data.get('establecimiento', ESTABLECIMIENTO),
            data.get('codigo_utp', CODIGO_ESTABLECIMIENTO),
            data.get('sector', ''),
            data.get('jornada_completa', 'Sí'),
            sae_asignacion,
            certificado_nacimiento,
            situacion_academica,
            apoderado_poder_simple
        ))

        # Si existe un usuario apoderado con el mismo nombre completo, asociar esta matrícula al apoderado
        apoderado_nombre = data.get('apoderado_nombre', '').strip()
        if apoderado_nombre:
            cursor.execute(
                'SELECT id FROM users WHERE rol = ? AND (LOWER(nombre_completo) = LOWER(?) OR LOWER(username) = LOWER(?))',
                ('apoderado', apoderado_nombre, apoderado_nombre)
            )
            apoderado_usuario = cursor.fetchone()
            if apoderado_usuario:
                apoderado_user_id = apoderado_usuario[0]
                cursor.execute(
                    'INSERT OR IGNORE INTO apoderados (user_id, alumno_rut, relacion) VALUES (?, ?, ?)',
                    (apoderado_user_id, alumno_rut, 'titular')
                )

        conn.commit()
        conn.close()

        logger.info(f"Matrícula creada para alumno {data.get('alumno_nombre')} (RUT: {alumno_rut}) por {session.get('user')}")

        if apoderado_email:
            if send_email_to_apoderado(apoderado_email, data.get('apoderado_nombre', ''), data.get('alumno_nombre', ''), data.get('alumno_rut', '')):
                flash("Matrícula guardada correctamente y correo enviado al apoderado")
            else:
                flash("Matrícula guardada correctamente, pero no se pudo enviar el correo al apoderado")
        else:
            flash("Matrícula guardada correctamente")

        return redirect('/lista')
    except Exception as e:
        flash(f"Error al guardar: {str(e)}")
        return redirect('/')

@app.route('/lista')
def lista():
    if 'user' not in session:
        return redirect('/')
    
    # Solo admin, administrativo y docente pueden ver la lista
    if session.get('rol') not in ['admin', 'administrativo', 'docente']:
        flash("No tienes permisos para ver esto")
        return redirect('/')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM matriculas ORDER BY id DESC")
    datos = cursor.fetchall()
    conn.close()

    return render_template('lista.html', datos=datos)

@app.route('/export_matriculas_sige')
def export_matriculas_sige():
    if 'user' not in session or session.get('rol') not in ['admin', 'administrativo']:
        return redirect('/')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM matriculas ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Código UTP',
        'Establecimiento',
        'Año Escolar',
        'Grado',
        'Sección',
        'Jornada',
        'Jornada Completa',
        'Código Sector',
        'RUT Alumno',
        'Nombre Alumno',
        'Fecha Nacimiento',
        'Dirección Alumno',
        'Teléfono Alumno',
        'RUT Apoderado',
        'Nombre Apoderado',
        'Teléfono Apoderado',
        'Email Apoderado',
        'Dirección Apoderado',
        'RUT Suplente',
        'Nombre Suplente',
        'Teléfono Suplente',
        'Dirección Suplente',
        'Tipo Matrícula',
        'Estado Matrícula',
        'Fecha Matrícula',
        'SAE Asignación',
        'Certificado Nacimiento',
        'Situación Académica',
        'Poder Simple Apoderado'
    ])

    for row in rows:
        writer.writerow([
            row[23],
            row[22],
            row[14],
            row[15],
            row[16],
            row[17],
            row[25],
            row[24],
            row[2],
            row[1],
            row[18],
            row[3],
            row[4],
            row[6],
            row[5],
            row[7],
            row[8],
            row[9],
            row[11],
            row[10],
            row[12],
            row[13],
            row[19],
            row[20],
            row[21],
            row[26] if len(row) > 26 else '',
            row[27] if len(row) > 27 else '',
            row[28] if len(row) > 28 else '',
            row[29] if len(row) > 29 else ''
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='matriculas_sige.csv'
    )

@app.route('/download_matriculas_sige_ejemplo')
def download_matriculas_sige_ejemplo():
    sample_path = os.path.join(app.root_path, 'matriculas_sige_ejemplo.csv')
    if not os.path.exists(sample_path):
        flash('Archivo de ejemplo no disponible')
        return redirect('/import_matriculas_sige')

    return send_file(
        sample_path,
        mimetype='text/csv',
        as_attachment=True,
        download_name='matriculas_sige_ejemplo.csv'
    )

@app.route('/import_matriculas_sige', methods=['GET', 'POST'])
def import_matriculas_sige():
    if 'user' not in session or session.get('rol') not in ['admin', 'administrativo']:
        return redirect('/')

    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or file.filename == '':
            flash('Selecciona un archivo CSV para importar')
            return redirect('/import_matriculas_sige')

        try:
            stream = file.stream.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(stream))
            conn = get_db()
            cursor = conn.cursor()
            inserted = 0

            for row in reader:
                alumno_rut = normalizar_rut(row.get('RUT Alumno', ''))
                if not alumno_rut or not row.get('Nombre Alumno'):
                    continue

                cursor.execute('''
                    INSERT INTO matriculas (
                        alumno_nombre, alumno_rut, alumno_direccion, alumno_telefono,
                        apoderado_nombre, apoderado_rut, apoderado_telefono, apoderado_email,
                        apoderado_direccion, suplente_nombre, suplente_rut, suplente_telefono,
                        suplente_direccion, ano_escolar, grado, seccion, jornada,
                        fecha_nacimiento, tipo_matricula, estado_matricula, fecha_matricula,
                        establecimiento, codigo_utp, sector, jornada_completa,
                        sae_asignacion, certificado_nacimiento, situacion_academica,
                        apoderado_poder_simple
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row.get('Nombre Alumno', ''),
                    alumno_rut,
                    row.get('Dirección Alumno', ''),
                    row.get('Teléfono Alumno', ''),
                    row.get('Nombre Apoderado', ''),
                    normalizar_rut(row.get('RUT Apoderado', '')),
                    row.get('Teléfono Apoderado', ''),
                    row.get('Email Apoderado', ''),
                    row.get('Dirección Apoderado', ''),
                    row.get('Nombre Suplente', ''),
                    normalizar_rut(row.get('RUT Suplente', '')),
                    row.get('Teléfono Suplente', ''),
                    row.get('Dirección Suplente', ''),
                    row.get('Año Escolar', ''),
                    row.get('Grado', ''),
                    row.get('Sección', ''),
                    row.get('Jornada', ''),
                    row.get('Fecha Nacimiento', ''),
                    row.get('Tipo Matrícula', 'Nueva'),
                    row.get('Estado Matrícula', 'Matriculado'),
                    row.get('Fecha Matrícula', datetime.now().strftime('%Y-%m-%d')),
                    row.get('Establecimiento', ESTABLECIMIENTO),
                    row.get('Código UTP', CODIGO_ESTABLECIMIENTO),
                    row.get('Código Sector', ''),
                    row.get('Jornada Completa', 'Sí'),
                    row.get('SAE Asignación', ''),
                    row.get('Certificado Nacimiento', ''),
                    row.get('Situación Académica', ''),
                    row.get('Poder Simple Apoderado', '')
                ))
                inserted += 1

            conn.commit()
            conn.close()
            flash(f'Importación completada: {inserted} matrículas')
            return redirect('/lista')
        except Exception as e:
            flash(f'Error importando CSV: {e}')
            return redirect('/import_matriculas_sige')

    return render_template('import_matriculas.html')

@app.route('/eliminar_matricula/<int:id>')
def eliminar_matricula(id):
    if 'user' not in session or session.get('rol') != 'admin':
        flash("No tienes permisos para eliminar matrículas")
        return redirect('/lista')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM matriculas WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Matrícula eliminada correctamente")
    return redirect('/lista')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/asistencia_alumno/<rut>')
def asistencia_alumno(rut):
    if 'user' not in session:
        return redirect('/')
    
    rol = session.get('rol')
    
    # Si es apoderado, verificar que el RUT sea de su hijo
    if rol == 'apoderado':
        user_id = session.get('user_id')
        asociar_matriculas_apoderado(user_id)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM apoderados 
            WHERE user_id = ? AND alumno_rut = ?
        ''', (user_id, rut))
        if cursor.fetchone()[0] == 0:
            conn.close()
            flash("No tienes acceso a esta información")
            return redirect('/dashboard_apoderado')
        conn.close()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener datos del alumno
    cursor.execute('''
        SELECT * FROM matriculas WHERE alumno_rut = ?
    ''', (rut,))
    alumno = cursor.fetchone()
    
    if not alumno:
        flash("Alumno no encontrado")
        return redirect('/lista')
    
    # Obtener asistencia del alumno
    cursor.execute('''
        SELECT * FROM asistencia WHERE alumno_rut = ? ORDER BY fecha DESC
    ''', (rut,))
    registros_asistencia = cursor.fetchall()
    
    # Calcular estadísticas
    presentes = sum(1 for r in registros_asistencia if r[4] == 1)
    ausentes = sum(1 for r in registros_asistencia if r[4] == 0)
    total = len(registros_asistencia)
    porcentaje = round((presentes / total) * 100, 1) if total > 0 else 0
    
    conn.close()
    
    return render_template('asistencia_alumno.html', 
                         alumno=alumno, 
                         registros=registros_asistencia,
                         presentes=presentes,
                         ausentes=ausentes,
                         total=total,
                         porcentaje=porcentaje)

@app.route('/asistencia', methods=['GET', 'POST'])
def asistencia():
    if 'user' not in session:
        return redirect('/')
    
    # Solo admin y administrativo pueden registrar asistencia
    if session.get('rol') not in ['admin', 'administrativo']:
        flash("No tienes permisos para registrar asistencia")
        return redirect('/')
    
    if request.method == 'POST':
        data = request.form
        fecha = data.get('fecha')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Obtener todos los alumnos matriculados
        cursor.execute("SELECT alumno_nombre, alumno_rut FROM matriculas")
        alumnos = cursor.fetchall()
        
        for alumno_nombre, alumno_rut in alumnos:
            presente = data.get(f'presente_{alumno_nombre}_{alumno_rut}')
            
            # Verificar si ya existe registro para este alumno en esta fecha
            cursor.execute(
                "SELECT id FROM asistencia WHERE alumno_rut=? AND fecha=?",
                (alumno_rut, fecha)
            )
            existe = cursor.fetchone()
            
            if existe:
                # Actualizar
                cursor.execute(
                    "UPDATE asistencia SET presente=? WHERE alumno_rut=? AND fecha=?",
                    (1 if presente else 0, alumno_rut, fecha)
                )
            else:
                # Insertar
                cursor.execute('''
                    INSERT INTO asistencia (alumno_nombre, alumno_rut, fecha, presente)
                    VALUES (?, ?, ?, ?)
                ''', (alumno_nombre, alumno_rut, fecha, 1 if presente else 0))
        
        conn.commit()
        conn.close()
        
        flash("Asistencia registrada correctamente")
        return redirect('/asistencia')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT alumno_nombre, alumno_rut FROM matriculas ORDER BY alumno_nombre")
    alumnos = cursor.fetchall()
    conn.close()
    
    return render_template('asistencia.html', alumnos=alumnos)

@app.route('/asistencia_docente', methods=['GET', 'POST'])
def asistencia_docente():
    if 'user' not in session:
        return redirect('/')
    
    # Solo docentes pueden acceder
    if session.get('rol') != 'docente':
        flash("No tienes permisos para registrar asistencia")
        return redirect('/')
    
    if request.method == 'POST':
        data = request.form
        fecha = data.get('fecha')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Obtener todos los alumnos matriculados
        cursor.execute("SELECT alumno_nombre, alumno_rut FROM matriculas")
        alumnos = cursor.fetchall()
        
        for alumno_nombre, alumno_rut in alumnos:
            presente = data.get(f'presente_{alumno_nombre}_{alumno_rut}')
            
            # Verificar si ya existe registro para este alumno en esta fecha
            cursor.execute(
                "SELECT id FROM asistencia WHERE alumno_rut=? AND fecha=?",
                (alumno_rut, fecha)
            )
            existe = cursor.fetchone()
            
            if existe:
                # Actualizar
                cursor.execute(
                    "UPDATE asistencia SET presente=? WHERE alumno_rut=? AND fecha=?",
                    (1 if presente else 0, alumno_rut, fecha)
                )
            else:
                # Insertar
                cursor.execute('''
                    INSERT INTO asistencia (alumno_nombre, alumno_rut, fecha, presente)
                    VALUES (?, ?, ?, ?)
                ''', (alumno_nombre, alumno_rut, fecha, 1 if presente else 0))
        
        conn.commit()
        conn.close()
        
        flash("Asistencia registrada exitosamente")
        return redirect('/dashboard_docente')
    
    # GET: mostrar formulario
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT alumno_nombre, alumno_rut FROM matriculas")
    alumnos = cursor.fetchall()
    conn.close()
    
    return render_template('asistencia_docente.html', alumnos=alumnos)

@app.route('/guardar_asistencia', methods=['POST'])
def guardar_asistencia():
    if 'user' not in session:
        return redirect('/')
    
    data = request.form
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO asistencia (alumno_nombre, alumno_rut, fecha, presente)
        VALUES (?, ?, ?, ?)
    ''', (
        data['alumno_nombre'],
        data['alumno_rut'],
        data['fecha'],
        1 if 'presente' in data else 0
    ))
    
    conn.commit()
    conn.close()
    
    flash("Asistencia registrada correctamente")
    return redirect('/asistencia')

@app.route('/lista_asistencia')
def lista_asistencia():
    if 'user' not in session:
        return redirect('/')
    
    rol = session.get('rol')
    user_id = session.get('user_id')
    filtro_fecha = request.args.get('fecha')
    filtro_alumno = request.args.get('alumno')
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM asistencia WHERE 1=1"
    params = []
    
    # Si es apoderado, solo ver asistencia de sus alumnos
    if rol == 'apoderado':
        asociar_matriculas_apoderado(user_id)
        cursor.execute('''
            SELECT alumno_rut FROM apoderados WHERE user_id = ?
        ''', (user_id,))
        ruts = [row[0] for row in cursor.fetchall()]
        
        if ruts:
            placeholders = ','.join('?' * len(ruts))
            query += f" AND alumno_rut IN ({placeholders})"
            params.extend(ruts)
        else:
            query += " AND 1=0"  # Si no tiene alumnos, no mostrar nada
    
    if filtro_fecha:
        query += " AND fecha = ?"
        params.append(filtro_fecha)
    
    if filtro_alumno:
        query += " AND alumno_nombre LIKE ?"
        params.append(f"%{filtro_alumno}%")
    
    query += " ORDER BY fecha DESC, alumno_nombre"
    
    cursor.execute(query, params)
    registros = cursor.fetchall()
    
    # Obtener estadísticas
    if rol == 'apoderado':
        # Solo estadísticas de los alumnos del apoderado
        cursor.execute('''
            SELECT m.alumno_nombre, m.alumno_rut FROM matriculas m
            JOIN apoderados a ON m.alumno_rut = a.alumno_rut
            WHERE a.user_id = ?
            ORDER BY m.alumno_nombre
        ''', (user_id,))
        alumnos = cursor.fetchall()
    else:
        cursor.execute("SELECT DISTINCT alumno_nombre, alumno_rut FROM matriculas ORDER BY alumno_nombre")
        alumnos = cursor.fetchall()
    
    stats = {}
    for alumno_nombre, alumno_rut in alumnos:
        cursor.execute("SELECT COUNT(*) FROM asistencia WHERE alumno_rut=? AND presente=1", (alumno_rut,))
        presentes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM asistencia WHERE alumno_rut=? AND presente=0", (alumno_rut,))
        ausentes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM asistencia WHERE alumno_rut=?", (alumno_rut,))
        total = cursor.fetchone()[0]
        
        if total > 0:
            porcentaje = round((presentes / total) * 100, 1)
            stats[alumno_nombre] = {
                'presentes': presentes,
                'ausentes': ausentes,
                'total': total,
                'porcentaje': porcentaje
            }
    
    conn.close()
    
    return render_template('lista_asistencia.html', registros=registros, stats=stats, alumnos=alumnos, rol=rol)

@app.route('/eliminar_asistencia/<int:id>')
def eliminar_asistencia(id):
    if 'user' not in session:
        return redirect('/')
    
    # Solo admin y administrativo pueden eliminar
    if session.get('rol') not in ['admin', 'administrativo']:
        flash("No tienes permisos para eliminar registros")
        return redirect('/lista_asistencia')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM asistencia WHERE id=?", (id,))
    conn.commit()
    conn.close()
    
    flash("Registro de asistencia eliminado")
    return redirect('/lista_asistencia')

@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'user' not in session or session.get('rol') != 'admin':
        flash("No tienes permisos para acceder a esta página")
        return redirect('/')
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        rol = request.form['rol']
        nombre_completo = request.form['nombre_completo']
        asignatura = request.form.get('asignatura', None)
        
        # Validar que el username no exista
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username=?", (username,))
        if cursor.fetchone():
            flash("El nombre de usuario ya existe")
            conn.close()
            return redirect('/crear_usuario')
        
        try:
            password_hash = hash_password(password)
            cursor.execute('''
                INSERT INTO users (username, password, rol, nombre_completo, asignatura)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, password_hash, rol, nombre_completo, asignatura))
            conn.commit()
            conn.close()
            
            logger.info(f"Usuario {username} ({rol}) creado por administrador {session.get('user')}")
            
            flash("Usuario creado correctamente")
            return redirect('/dashboard')
        except Exception as e:
            flash(f"Error al crear usuario: {str(e)}")
            conn.close()
            return redirect('/crear_usuario')
    
    return render_template('crear_usuario.html')

@app.route('/perfil_docente', methods=['GET', 'POST'])
def perfil_docente():
    usuario_actual_sesion = session.get('usuario') or session.get('user')
    if not usuario_actual_sesion or session.get('rol') != 'docente':
        return redirect('/login')
    
    if request.method == 'POST':
        usuario = request.form['usuario']
        password_actual = request.form.get('password_actual', '')
        password_nueva = request.form.get('password_nueva', '')
        password_confirmar = request.form.get('password_confirmar', '')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar usuario actual
        cursor.execute('SELECT password FROM users WHERE username = ?', (usuario_actual_sesion,))
        user_actual = cursor.fetchone()
        
        if not user_actual:
            conn.close()
            flash("Usuario no encontrado")
            return redirect('/perfil_docente')
        
        # Si se quiere cambiar contraseña
        if password_nueva:
            if not password_actual:
                conn.close()
                flash("Debes ingresar la contraseña actual para cambiarla")
                return redirect('/perfil_docente')
            
            if not verify_password(user_actual[0], password_actual):
                conn.close()
                flash("Contraseña actual incorrecta")
                return redirect('/perfil_docente')
            
            if password_nueva != password_confirmar:
                conn.close()
                flash("Las contraseñas nuevas no coinciden")
                return redirect('/perfil_docente')
            
            if len(password_nueva) < 6:
                conn.close()
                flash("La nueva contraseña debe tener al menos 6 caracteres")
                return redirect('/perfil_docente')
        
        try:
            if password_nueva:
                cursor.execute('''
                    UPDATE users SET username = ?, password = ? WHERE username = ?
                ''', (usuario, hash_password(password_nueva), usuario_actual_sesion))
            else:
                cursor.execute('''
                    UPDATE users SET username = ? WHERE username = ?
                ''', (usuario, usuario_actual_sesion))
            conn.commit()
            conn.close()
            
            session['usuario'] = usuario
            session['user'] = usuario
            flash("Perfil actualizado correctamente")
            return redirect('/perfil_docente')
        except Exception as e:
            conn.close()
            flash(f"Error al actualizar perfil: {str(e)}")
            return redirect('/perfil_docente')

@app.route('/gestionar_usuarios')
def gestionar_usuarios():
    current_user = session.get('usuario') or session.get('user')
    if not current_user or session.get('rol') != 'admin':
        return redirect('/login')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, nombre_completo, rol, asignatura FROM users ORDER BY rol, username')
    usuarios = cursor.fetchall()
    conn.close()

    return render_template('gestionar_usuarios.html', usuarios=usuarios)

@app.route('/editar_usuario/<int:user_id>', methods=['GET', 'POST'])
def editar_usuario(user_id):
    current_user = session.get('usuario') or session.get('user')
    if not current_user or session.get('rol') != 'admin':
        return redirect('/login')

    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        usuario = request.form['usuario']
        rol = request.form['rol']
        asignatura = request.form.get('asignatura', '')
        password_nueva = request.form.get('password_nueva', '')

        try:
            if password_nueva:
                if len(password_nueva) < 6:
                    flash("La contraseña debe tener al menos 6 caracteres")
                    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
                    usuario_data = cursor.fetchone()
                    conn.close()
                    return render_template('editar_usuario.html', usuario=usuario_data)

                cursor.execute('''
                    UPDATE users SET username = ?, rol = ?, asignatura = ?, password = ? WHERE id = ?
                ''', (usuario, rol, asignatura if rol == 'docente' else None, hash_password(password_nueva), user_id))
            else:
                cursor.execute('''
                    UPDATE users SET username = ?, rol = ?, asignatura = ? WHERE id = ?
                ''', (usuario, rol, asignatura if rol == 'docente' else None, user_id))

            conn.commit()
            conn.close()

            flash("Usuario actualizado correctamente")
            return redirect('/gestionar_usuarios')
        except Exception as e:
            conn.close()
            flash(f"Error al actualizar usuario: {str(e)}")
            return redirect(f'/editar_usuario/{user_id}')

    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    usuario = cursor.fetchone()
    conn.close()

    if not usuario:
        flash("Usuario no encontrado")
        return redirect('/gestionar_usuarios')

    return render_template('editar_usuario.html', usuario=usuario)

@app.route('/eliminar_usuario/<int:user_id>')
def eliminar_usuario(user_id):
    current_user = session.get('usuario') or session.get('user')
    if not current_user or session.get('rol') != 'admin':
        return redirect('/login')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verificar que no sea el último admin
    cursor.execute('SELECT rol, username FROM users WHERE id = ?', (user_id,))
    usuario_a_eliminar = cursor.fetchone()
    
    if usuario_a_eliminar and usuario_a_eliminar[0] == 'admin':
        cursor.execute('SELECT COUNT(*) FROM users WHERE rol = "admin"')
        admin_count = cursor.fetchone()[0]
        if admin_count <= 1:
            conn.close()
            flash("No puedes eliminar el último administrador del sistema")
            return redirect('/gestionar_usuarios')
    
    try:
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        username_eliminado = usuario_a_eliminar[1] if usuario_a_eliminar and len(usuario_a_eliminar) > 1 else str(user_id)
        logger.info(f"Usuario {username_eliminado} eliminado por administrador {session.get('user')}")
        
        flash("Usuario eliminado correctamente")
    except Exception as e:
        conn.close()
        flash(f"Error al eliminar usuario: {str(e)}")
    
    return redirect('/gestionar_usuarios')

@app.route('/solicitar_permiso', methods=['GET', 'POST'])
def solicitar_permiso():
    if 'user' not in session or session.get('rol') not in ['administrativo', 'docente']:
        flash("No tienes permisos para acceder a esta página")
        return redirect('/')
    
    if request.method == 'POST':
        permiso = request.form['permiso']
        descripcion = request.form['descripcion']
        user_id = session['user_id']
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO permisos_solicitados (user_id, permiso, descripcion, fecha_solicitud)
            VALUES (?, ?, ?, ?)
        ''', (user_id, permiso, descripcion, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        
        flash("Solicitud de permiso enviada al administrador")
        return redirect('/dashboard')
    
    return render_template('solicitar_permiso.html')

@app.route('/admin/permisos')
def admin_permisos():
    if 'user' not in session or session.get('rol') != 'admin':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ps.id, ps.permiso, ps.descripcion, ps.estado, ps.fecha_solicitud, u.username, u.nombre_completo
        FROM permisos_solicitados ps
        JOIN users u ON ps.user_id = u.id
        ORDER BY ps.fecha_solicitud DESC
    ''')
    solicitudes = cursor.fetchall()
    conn.close()
    
    return render_template('admin_permisos.html', solicitudes=solicitudes)

@app.route('/admin/aprobar_permiso/<int:id>')
def aprobar_permiso(id):
    if 'user' not in session or session.get('rol') != 'admin':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE permisos_solicitados SET estado = "aprobado", fecha_respuesta = ? WHERE id = ?',
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), id))
    conn.commit()
    conn.close()
    
    flash("Permiso aprobado")
    return redirect('/admin/permisos')

@app.route('/admin/rechazar_permiso/<int:id>')
def rechazar_permiso(id):
    if 'user' not in session or session.get('rol') != 'admin':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE permisos_solicitados SET estado = "rechazado", fecha_respuesta = ? WHERE id = ?',
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), id))
    conn.commit()
    conn.close()
    
    flash("Permiso rechazado")
    return redirect('/admin/permisos')

@app.route('/chat/<int:solicitud_id>', methods=['GET', 'POST'])
def chat(solicitud_id):
    if 'user' not in session:
        return redirect('/')
    
    user_id = session['user_id']
    rol = session['rol']
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verificar que el usuario tenga acceso a esta solicitud
    cursor.execute('SELECT user_id FROM permisos_solicitados WHERE id = ?', (solicitud_id,))
    solicitud = cursor.fetchone()
    if not solicitud:
        conn.close()
        flash("Solicitud no encontrada")
        return redirect('/')
    
    solicitante_id = solicitud[0]
    
    if rol != 'admin' and user_id != solicitante_id:
        conn.close()
        flash("No tienes acceso a este chat")
        return redirect('/')
    
    if request.method == 'POST':
        mensaje = request.form['mensaje'].strip()
        if mensaje:
            cursor.execute('INSERT INTO chat_mensajes (solicitud_id, user_id, mensaje, fecha) VALUES (?, ?, ?, ?)',
                           (solicitud_id, user_id, mensaje, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
    
    # Obtener mensajes
    cursor.execute('''
        SELECT cm.mensaje, cm.fecha, u.nombre_completo, u.rol, cm.user_id
        FROM chat_mensajes cm
        JOIN users u ON cm.user_id = u.id
        WHERE cm.solicitud_id = ?
        ORDER BY cm.fecha
    ''', (solicitud_id,))
    mensajes = cursor.fetchall()
    
    conn.close()
    
    return render_template('chat.html', mensajes=mensajes, solicitud_id=solicitud_id)

@app.route('/chat_informe/<int:solicitud_id>', methods=['GET', 'POST'])
def chat_informe(solicitud_id):
    if 'user' not in session:
        return redirect('/')
    
    user_id = session['user_id']
    rol = session['rol']
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verificar que el usuario tenga acceso a esta solicitud de informe
    cursor.execute('SELECT apoderado_id FROM solicitudes_informes WHERE id = ?', (solicitud_id,))
    solicitud = cursor.fetchone()
    if not solicitud:
        conn.close()
        flash("Solicitud de informe no encontrada")
        return redirect('/')
    
    apoderado_id = solicitud[0]
    
    if rol not in ['admin', 'administrativo'] and user_id != apoderado_id:
        conn.close()
        flash("No tienes acceso a este chat de informe")
        return redirect('/')
    
    if request.method == 'POST':
        mensaje = request.form['mensaje'].strip()
        if mensaje:
            cursor.execute('INSERT INTO chat_informes_mensajes (solicitud_id, user_id, mensaje, fecha) VALUES (?, ?, ?, ?)',
                           (solicitud_id, user_id, mensaje, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
    
    # Obtener mensajes
    cursor.execute('''
        SELECT cim.mensaje, cim.fecha, u.nombre_completo, u.rol, cim.user_id
        FROM chat_informes_mensajes cim
        JOIN users u ON cim.user_id = u.id
        WHERE cim.solicitud_id = ?
        ORDER BY cim.fecha
    ''', (solicitud_id,))
    mensajes = cursor.fetchall()
    
    conn.close()
    
    return render_template('chat_informe.html', mensajes=mensajes, solicitud_id=solicitud_id, rol=rol)

@app.route('/solicitar_informe', methods=['GET', 'POST'])
def solicitar_informe():
    if 'user' not in session or session.get('rol') != 'apoderado':
        flash("Solo los apoderados pueden solicitar informes")
        return redirect('/')
    
    user_id = session['user_id']
    
    try:
        asociar_matriculas_apoderado(user_id)

        conn = get_db()
        cursor = conn.cursor()
        
        # Obtener los alumnos asociados al apoderado
        cursor.execute('SELECT alumno_rut FROM apoderados WHERE user_id = ?', (user_id,))
        alumnos = cursor.fetchall()
        
        if not alumnos:
            conn.close()
            flash("No tienes alumnos asociados. Contacta al administrativo.")
            return redirect('/dashboard_apoderado')
        
        if request.method == 'POST':
            alumno_rut = request.form['alumno_rut']
            tipo_informe = request.form['tipo_informe']
            descripcion = request.form['descripcion']
            
            # Verificar que el alumno pertenezca al apoderado
            if not any(alumno[0] == alumno_rut for alumno in alumnos):
                conn.close()
                flash("No tienes permisos para solicitar informes de este alumno")
                return redirect('/dashboard_apoderado')
            
            cursor.execute('''
                INSERT INTO solicitudes_informes (apoderado_id, alumno_rut, tipo_informe, descripcion, fecha_solicitud)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, alumno_rut, tipo_informe, descripcion, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            conn.close()
            
            flash("Solicitud de informe enviada al administrativo para aprobación")
            return redirect('/dashboard_apoderado')
        
        # Obtener nombres de alumnos para mostrar en el formulario
        alumno_ruts = [alumno[0] for alumno in alumnos]
        placeholders = ','.join('?' * len(alumno_ruts))
        cursor.execute(f'SELECT alumno_rut, alumno_nombre FROM matriculas WHERE alumno_rut IN ({placeholders})', alumno_ruts)
        alumnos_info = cursor.fetchall()
        
        conn.close()
        
        return render_template('solicitar_informe.html', alumnos=alumnos_info)
    
    except Exception as e:
        logger.error(f"Error en solicitar_informe para user_id {user_id}: {str(e)}")
        flash("Ocurrió un error al procesar tu solicitud. Inténtalo nuevamente.")
        return redirect('/dashboard_apoderado')

@app.route('/calificaciones')
def calificaciones():
    if 'user' not in session:
        return redirect('/')
    
    rol = session.get('rol')
    user_id = session.get('user_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    if rol == 'docente':
        # Docente ve calificaciones de sus asignaturas
        asignatura = session.get('asignatura')
        cursor.execute('''
            SELECT c.id, c.alumno_rut, m.alumno_nombre, c.asignatura, c.nota, c.fecha, c.comentario
            FROM calificaciones c
            JOIN matriculas m ON c.alumno_rut = m.alumno_rut
            WHERE c.docente_id = ? AND c.asignatura = ?
            ORDER BY c.fecha DESC
        ''', (user_id, asignatura))
    elif rol == 'apoderado':
        asociar_matriculas_apoderado(user_id)
        cursor.execute('''
            SELECT c.id, c.alumno_rut, m.alumno_nombre, c.asignatura, c.nota, c.fecha, c.comentario, u.nombre_completo as docente
            FROM calificaciones c
            JOIN matriculas m ON c.alumno_rut = m.alumno_rut
            JOIN apoderados a ON c.alumno_rut = a.alumno_rut
            JOIN users u ON c.docente_id = u.id
            WHERE a.user_id = ?
            ORDER BY c.fecha DESC
        ''', (user_id,))
    else:
        # Admin/administrativo ven todas
        cursor.execute('''
            SELECT c.id, c.alumno_rut, m.alumno_nombre, c.asignatura, c.nota, c.fecha, c.comentario, u.nombre_completo as docente
            FROM calificaciones c
            JOIN matriculas m ON c.alumno_rut = m.alumno_rut
            JOIN users u ON c.docente_id = u.id
            ORDER BY c.fecha DESC
        ''')
    
    califs = cursor.fetchall()
    conn.close()
    
    return render_template('calificaciones.html', calificaciones=califs, rol=rol)

@app.route('/agregar_calificacion', methods=['GET', 'POST'])
def agregar_calificacion():
    if 'user' not in session or session.get('rol') != 'docente':
        return redirect('/')
    
    if request.method == 'POST':
        alumno_rut = request.form['alumno_rut']
        asignatura = session.get('asignatura')
        nota = float(request.form['nota'])
        comentario = request.form.get('comentario', '')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO calificaciones (alumno_rut, asignatura, docente_id, nota, fecha, comentario)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (alumno_rut, asignatura, session.get('user_id'), nota, datetime.now().strftime('%Y-%m-%d'), comentario))
        conn.commit()
        conn.close()
        
        logger.info(f"Calificación agregada para alumno {alumno_rut} en {asignatura} por docente {session.get('user')}")
        flash("Calificación agregada correctamente")
        return redirect('/calificaciones')
    
    # Obtener alumnos para el docente
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT alumno_rut, alumno_nombre FROM matriculas ORDER BY alumno_nombre")
    alumnos = cursor.fetchall()
    conn.close()
    
    return render_template('agregar_calificacion.html', alumnos=alumnos)

@app.route('/editar_calificacion/<int:id>', methods=['GET', 'POST'])
def editar_calificacion(id):
    if 'user' not in session or session.get('rol') not in ['admin', 'docente']:
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM calificaciones WHERE id = ?', (id,))
    calif = cursor.fetchone()
    if not calif:
        conn.close()
        flash("Calificación no encontrada")
        return redirect('/calificaciones')
    
    if session.get('rol') == 'docente' and calif[3] != session.get('user_id'):
        conn.close()
        flash("No tienes permisos para editar esta calificación")
        return redirect('/calificaciones')
        
    if request.method == 'POST':
        nota = float(request.form['nota'])
        comentario = request.form.get('comentario', '')
        
        cursor.execute('UPDATE calificaciones SET nota = ?, comentario = ? WHERE id = ?', (nota, comentario, id))
        conn.commit()
        conn.close()
        
        flash("Calificación actualizada correctamente")
        return redirect('/calificaciones')
        
    cursor.execute('SELECT alumno_nombre FROM matriculas WHERE alumno_rut = ?', (calif[1],))
    alumno = cursor.fetchone()
    alumno_nombre = alumno[0] if alumno else calif[1]
    
    conn.close()
    return render_template('editar_calificacion.html', calif=calif, alumno_nombre=alumno_nombre)

@app.route('/eliminar_calificacion/<int:id>')
def eliminar_calificacion(id):
    if 'user' not in session or session.get('rol') not in ['admin', 'docente']:
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT docente_id FROM calificaciones WHERE id = ?', (id,))
    calif = cursor.fetchone()
    if not calif:
        conn.close()
        flash("Calificación no encontrada")
        return redirect('/calificaciones')
        
    if session.get('rol') == 'docente' and calif[0] != session.get('user_id'):
        conn.close()
        flash("No tienes permisos para eliminar esta calificación")
        return redirect('/calificaciones')
        
    cursor.execute('DELETE FROM calificaciones WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    flash("Calificación eliminada correctamente")
    return redirect('/calificaciones')

@app.route('/horarios')
def horarios():
    if 'user' not in session:
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT h.id, h.asignatura, u.nombre_completo as docente, h.dia_semana, h.hora_inicio, h.hora_fin, h.aula
        FROM horarios h
        JOIN users u ON h.docente_id = u.id
        ORDER BY h.dia_semana, h.hora_inicio
    ''')
    horarios_list = cursor.fetchall()
    conn.close()
    
    return render_template('horarios.html', horarios=horarios_list)

@app.route('/agregar_horario', methods=['GET', 'POST'])
def agregar_horario():
    if 'user' not in session or session.get('rol') not in ['admin', 'administrativo']:
        return redirect('/')
    
    if request.method == 'POST':
        asignatura = request.form['asignatura']
        docente_id = request.form['docente_id']
        dia_semana = request.form['dia_semana']
        hora_inicio = request.form['hora_inicio']
        hora_fin = request.form['hora_fin']
        aula = request.form['aula']
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO horarios (asignatura, docente_id, dia_semana, hora_inicio, hora_fin, aula)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (asignatura, docente_id, dia_semana, hora_inicio, hora_fin, aula))
        conn.commit()
        conn.close()
        
        logger.info(f"Horario agregado para {asignatura} por {session.get('user')}")
        flash("Horario agregado correctamente")
        return redirect('/horarios')
    
    # Obtener docentes
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre_completo, asignatura FROM users WHERE rol='docente'")
    docentes = cursor.fetchall()
    conn.close()
    
    return render_template('agregar_horario.html', docentes=docentes)

@app.route('/editar_horario/<int:id>', methods=['GET', 'POST'])
def editar_horario(id):
    if 'user' not in session or session.get('rol') not in ['admin', 'administrativo']:
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM horarios WHERE id = ?', (id,))
    horario = cursor.fetchone()
    if not horario:
        conn.close()
        flash("Horario no encontrado")
        return redirect('/horarios')
        
    if request.method == 'POST':
        asignatura = request.form['asignatura']
        docente_id = int(request.form['docente_id'])
        dia_semana = request.form['dia_semana']
        hora_inicio = request.form['hora_inicio']
        hora_fin = request.form['hora_fin']
        aula = request.form['aula']
        
        cursor.execute('''
            UPDATE horarios 
            SET asignatura = ?, docente_id = ?, dia_semana = ?, hora_inicio = ?, hora_fin = ?, aula = ? 
            WHERE id = ?
        ''', (asignatura, docente_id, dia_semana, hora_inicio, hora_fin, aula, id))
        conn.commit()
        conn.close()
        
        flash("Horario actualizado correctamente")
        return redirect('/horarios')
        
    cursor.execute("SELECT id, nombre_completo, asignatura FROM users WHERE rol='docente'")
    docentes = cursor.fetchall()
    conn.close()
    return render_template('editar_horario.html', horario=horario, docentes=docentes)

@app.route('/eliminar_horario/<int:id>')
def eliminar_horario(id):
    if 'user' not in session or session.get('rol') not in ['admin', 'administrativo']:
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM horarios WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    flash("Horario eliminado correctamente")
    return redirect('/horarios')

@app.route('/reporte_pdf/<tipo>')
def reporte_pdf(tipo):
    if 'user' not in session:
        return redirect('/')
    
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from io import BytesIO
    
    buffer = BytesIO()
    
    if tipo == 'matriculas':
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    else:
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        
    elements = []
    
    styles = getSampleStyleSheet()
    title = Paragraph(f"Reporte de {tipo.title()}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 15))
    
    conn = get_db()
    cursor = conn.cursor()
    
    if tipo == 'matriculas':
        cursor.execute(
            "SELECT alumno_rut, alumno_nombre, grado, seccion, jornada, apoderado_nombre, apoderado_telefono, estado_matricula, fecha_matricula FROM matriculas ORDER BY id DESC"
        )
        data = [[
            'RUT Alumno', 'Nombre Alumno', 'Grado', 'Sección', 'Jornada', 'Nombre Apoderado', 'Teléfono Apoderado', 'Estado', 'Fecha Matrícula'
        ]] + cursor.fetchall()
    elif tipo == 'asistencia':
        cursor.execute("SELECT a.alumno_nombre, a.fecha, a.presente FROM asistencia a ORDER BY a.fecha DESC LIMIT 100")
        data = [['Nombre Alumno', 'Fecha', 'Presente']] + [(row[0], row[1], 'Sí' if row[2] else 'No') for row in cursor.fetchall()]
    elif tipo == 'calificaciones':
        cursor.execute("SELECT m.alumno_nombre, c.asignatura, c.nota, c.fecha FROM calificaciones c JOIN matriculas m ON c.alumno_rut = m.alumno_rut")
        data = [['Nombre Alumno', 'Asignatura', 'Nota', 'Fecha']] + cursor.fetchall()
    else:
        data = [['Error', 'Tipo no válido']]
    
    conn.close()
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), (0, 0.2, 0.4)),
        ('TEXTCOLOR', (0, 0), (-1, 0), (1, 1, 1)),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, (0.8, 0.8, 0.8)),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [(1, 1, 1), (0.95, 0.95, 0.95)])
    ]))
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    
    logger.info(f"Reporte PDF generado para {tipo} por {session.get('user')}")
    return send_file(buffer, as_attachment=True, download_name=f'reporte_{tipo}.pdf', mimetype='application/pdf')

# API REST
@app.route('/api/matriculas')
def api_matriculas():
    if 'user' not in session:
        return {'error': 'No autorizado'}, 401

    user_rol = session.get('rol')
    conn = get_db()
    cursor = conn.cursor()

    if user_rol == 'apoderado':
        user_id = session.get('user_id')
        asociar_matriculas_apoderado(user_id)
        ruts = get_apoderado_ruts(user_id)
        if not ruts:
            conn.close()
            return {'matriculas': []}
        placeholders = ','.join('?' * len(ruts))
        cursor.execute(f"SELECT * FROM matriculas WHERE alumno_rut IN ({placeholders})", tuple(ruts))
    elif user_rol in ['admin', 'administrativo', 'docente']:
        cursor.execute("SELECT * FROM matriculas")
    else:
        conn.close()
        return {'error': 'No autorizado'}, 401

    matriculas = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    result = {'matriculas': [dict(zip(columns, row)) for row in matriculas]}
    conn.close()
    return result

@app.route('/api/asistencia')
def api_asistencia():
    if 'user' not in session:
        return {'error': 'No autorizado'}, 401

    user_rol = session.get('rol')
    conn = get_db()
    cursor = conn.cursor()

    if user_rol == 'apoderado':
        user_id = session.get('user_id')
        asociar_matriculas_apoderado(user_id)
        ruts = get_apoderado_ruts(user_id)
        if not ruts:
            conn.close()
            return {'asistencia': []}
        placeholders = ','.join('?' * len(ruts))
        cursor.execute(f"SELECT * FROM asistencia WHERE alumno_rut IN ({placeholders}) ORDER BY fecha DESC LIMIT 100", tuple(ruts))
    elif user_rol in ['admin', 'administrativo', 'docente']:
        cursor.execute("SELECT * FROM asistencia ORDER BY fecha DESC LIMIT 100")
    else:
        conn.close()
        return {'error': 'No autorizado'}, 401

    asistencia = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    result = {'asistencia': [dict(zip(columns, row)) for row in asistencia]}
    conn.close()
    return result

@app.route('/admin/informes')
def admin_informes():
    if 'user' not in session or session.get('rol') != 'admin':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT si.id, si.alumno_rut, si.tipo_informe, si.descripcion, si.estado, si.fecha_solicitud, 
               u.nombre_completo as apoderado_nombre, m.alumno_nombre as alumno_nombre
        FROM solicitudes_informes si
        JOIN users u ON si.apoderado_id = u.id
        LEFT JOIN matriculas m ON si.alumno_rut = m.alumno_rut
        ORDER BY si.fecha_solicitud DESC
    ''')
    solicitudes = cursor.fetchall()
    conn.close()
    
    return render_template('admin_informes.html', solicitudes=solicitudes)

@app.route('/aprobar_informe/<int:informe_id>', methods=['POST'])
def aprobar_informe(informe_id):
    if 'user' not in session or session.get('rol') != 'admin':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE solicitudes_informes SET estado = "aprobado", fecha_respuesta = ?, administrativo_id = ? WHERE id = ?',
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session['user_id'], informe_id))
    conn.commit()
    conn.close()
    
    flash("Informe aprobado. El administrativo podrá imprimirlo.")
    return redirect('/admin/informes')

@app.route('/rechazar_informe/<int:informe_id>', methods=['POST'])
def rechazar_informe(informe_id):
    if 'user' not in session or session.get('rol') != 'admin':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE solicitudes_informes SET estado = "rechazado", fecha_respuesta = ? WHERE id = ?',
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), informe_id))
    conn.commit()
    conn.close()
    
    flash("Informe rechazado.")
    return redirect('/admin/informes')

@app.route('/administrativo/informes')
def administrativo_informes():
    if 'user' not in session or session.get('rol') != 'administrativo':
        return redirect('/')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT si.id, si.alumno_rut, si.tipo_informe, si.descripcion, si.estado, si.fecha_solicitud, 
               u.nombre_completo as apoderado_nombre, m.alumno_nombre as alumno_nombre
        FROM solicitudes_informes si
        JOIN users u ON si.apoderado_id = u.id
        LEFT JOIN matriculas m ON si.alumno_rut = m.alumno_rut
        WHERE si.estado = "aprobado"
        ORDER BY si.fecha_solicitud DESC
    ''')
    informes_aprobados = cursor.fetchall()
    conn.close()
    
    return render_template('administrativo_informes.html', informes=informes_aprobados)

if __name__ == '__main__':
    ngrok_token = os.getenv('NGROK_AUTH_TOKEN')
    if ngrok_token:
        ngrok.set_auth_token(ngrok_token)
        public_url = ngrok.connect(5000)
        print(f"Public URL: {public_url}")

    print("Servidor corriendo en http://localhost:5000")
    serve(app, host='0.0.0.0', port=5000)
