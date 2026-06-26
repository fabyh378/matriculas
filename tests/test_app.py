import pytest
import sqlite3
import os
import tempfile
import app as app_module
from app import app, validar_rut, normalizar_rut

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def db():
    # Crear DB de test en un archivo temporal único para evitar bloqueos
    fd, test_db = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(test_db)
    # Crear tablas básicas para tests
    conn.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            password TEXT,
            rol TEXT,
            nombre_completo TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE matriculas (
            id INTEGER PRIMARY KEY,
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
    conn.execute('''
        CREATE TABLE apoderados (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            alumno_rut TEXT,
            relacion TEXT
        )
    ''')
    conn.commit()
    conn.close()
    
    yield test_db
    
    # Limpiar
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except PermissionError:
            pass

def test_validar_rut():
    assert validar_rut('12345678-5')
    assert validar_rut('19766867-9')
    assert not validar_rut('12345678-9')
    assert validar_rut('IPA1234567')
    assert validar_rut('IPE7654321')
    assert not validar_rut('123456789')

def test_normalizar_rut():
    assert normalizar_rut('12.345.678-9') == '12345678-9'
    assert normalizar_rut('12 345 678 9') == '123456789'

def test_home_page(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Liceo' in response.data

def test_login_required_pages(client):
    response = client.get('/dashboard')
    assert response.status_code == 302  # Redirect to login

def test_export_matriculas_sige_header(client, db, monkeypatch):
    monkeypatch.setattr(app_module, 'DB', db)
    with sqlite3.connect(db) as conn:
        conn.execute('''
        INSERT INTO matriculas (
            id, alumno_nombre, alumno_rut, alumno_direccion, alumno_telefono,
            apoderado_nombre, apoderado_rut, apoderado_telefono, apoderado_email,
            apoderado_direccion, suplente_nombre, suplente_rut, suplente_telefono,
            suplente_direccion, ano_escolar, grado, seccion, jornada,
            fecha_nacimiento, tipo_matricula, estado_matricula, fecha_matricula,
            establecimiento, codigo_utp, sector, jornada_completa
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        1, 'Alumno Test', '11111111-1', 'Calle 123', '123456789',
        'Apoderado Test', '22222222-2', '987654321', 'apo@test.cl',
        'Calle Apoderado', 'Suplente Test', '33333333-3', '555555555',
        'Calle Suplente', '2025', '1 Medio', 'A', 'Mañana',
        '2008-05-15', 'Nueva', 'Matriculado', '2025-03-01', 'Liceo Test',
        '0000', 'Centro', 'Sí'
    ))

    with client.session_transaction() as sess:
        sess['user'] = 'admin'
        sess['rol'] = 'admin'

    response = client.get('/export_matriculas_sige')
    assert response.status_code == 200
    content = response.data.decode('utf-8-sig')
    assert content.splitlines()[0] == (
        'Código UTP,Establecimiento,Año Escolar,Grado,Sección,Jornada,Jornada Completa,'
        'Código Sector,RUT Alumno,Nombre Alumno,Fecha Nacimiento,Dirección Alumno,'
        'Teléfono Alumno,RUT Apoderado,Nombre Apoderado,Teléfono Apoderado,Email Apoderado,'
        'Dirección Apoderado,RUT Suplente,Nombre Suplente,Teléfono Suplente,Dirección Suplente,'
        'Tipo Matrícula,Estado Matrícula,Fecha Matrícula,SAE Asignación,Certificado Nacimiento,'
        'Situación Académica,Poder Simple Apoderado'
    )


def test_import_matriculas_sige_page(client):
    with client.session_transaction() as sess:
        sess['user'] = 'admin'
        sess['rol'] = 'admin'

    response = client.get('/import_matriculas_sige')
    assert response.status_code == 200
    assert b'Importar Matr' in response.data


def test_download_matriculas_sige_ejemplo(client):
    with client.session_transaction() as sess:
        sess['user'] = 'admin'
        sess['rol'] = 'admin'

    response = client.get('/download_matriculas_sige_ejemplo')
    assert response.status_code == 200
    assert b'matriculas_sige_ejemplo.csv' in response.headers.get('Content-Disposition', '').encode('utf-8')


def test_reporte_pdf_matriculas(client):
    with client.session_transaction() as sess:
        sess['user'] = 'admin'
        sess['rol'] = 'admin'

    response = client.get('/reporte_pdf/matriculas')
    assert response.status_code == 200
    assert response.headers.get('Content-Type') == 'application/pdf'


def test_api_matriculas_unauthorized(client):
    response = client.get('/api/matriculas')
    assert response.status_code == 401
    assert b'No autorizado' in response.data

def test_csrf_token_required_for_login(client):
    response = client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')

def test_login_with_csrf_token(client):
    response = client.get('/login')
    with client.session_transaction() as sess:
        token = sess.get('_csrf_token')

    response = client.post('/login', data={'username': 'admin', 'password': 'admin123', '_csrf_token': token}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Logout' not in response.data or b'Dashboard' in response.data

def test_api_matriculas_apoderado_limited(client, db, monkeypatch):
    monkeypatch.setattr(app_module, 'DB', db)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO users (username, password, rol, nombre_completo) VALUES (?, ?, ?, ?)",
                     ('apoderado2', 'pass', 'apoderado', 'Apoderado Test'))
        apoderado_id = conn.execute('SELECT id FROM users WHERE username = ?', ('apoderado2',)).fetchone()[0]
        conn.execute('''
            INSERT INTO matriculas (alumno_nombre, alumno_rut, apoderado_nombre, apoderado_rut, apoderado_email, ano_escolar, grado, seccion, jornada, fecha_nacimiento, tipo_matricula, estado_matricula, fecha_matricula, establecimiento, codigo_utp, sector, jornada_completa)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            'Alumno Test', '11111111-1', 'Apoderado Test', '22222222-2', 'apo@test.cl', '2025', '1 Medio', 'A', 'Mañana', '2008-05-15', 'Nueva', 'Matriculado', '2025-03-01', 'Liceo Test', '0000', 'Centro', 'Sí'
        ))
        conn.execute('INSERT INTO apoderados (user_id, alumno_rut, relacion) VALUES (?, ?, ?)',
                     (apoderado_id, '11111111-1', 'titular'))
        conn.commit()

    with client.session_transaction() as sess:
        sess['user'] = 'apoderado2'
        sess['user_id'] = apoderado_id
        sess['rol'] = 'apoderado'

    response = client.get('/api/matriculas')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['matriculas']) == 1
    assert data['matriculas'][0]['alumno_rut'] == '11111111-1'

if __name__ == '__main__':
    pytest.main()