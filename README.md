# Sistema de Gestión de Matrículas y Asistencia - Liceo Claudina Urrutia de Lavín

## Descripción

Este proyecto es una aplicación web desarrollada en Flask para la gestión integral de matrículas, asistencia y comunicación en el Liceo Claudina Urrutia de Lavín. Permite a administradores, personal administrativo, docentes y apoderados gestionar diversos aspectos del proceso educativo de manera eficiente y segura.

## Características Principales

### Gestión de Usuarios
- **Roles definidos**: Admin, Administrativo, Docente, Apoderado
- **Autenticación segura** con soporte para 2FA en cuentas de administrador
- **Creación, edición y eliminación** de usuarios por administradores
- **Perfiles personalizados** para cada rol

### Gestión de Matrículas
- **Registro de alumnos** con información completa (datos personales, apoderados, etc.)
- **Validación de RUT** chileno
- **Asociación automática** entre matrículas y usuarios apoderados
- **Envío de confirmaciones** por email a apoderados

### Control de Asistencia
- **Registro diario** de asistencia por alumno
- **Estadísticas detalladas** de presencia/ausencia
- **Filtros por fecha y alumno**
- **Vistas específicas** por rol (apoderados ven solo sus hijos)

### Sistema de Informes y Solicitudes
- **Solicitudes de informes** por parte de apoderados
- **Aprobación/rechazo** por administradores
- **Sistema de chat** integrado para comunicación
- **Historial completo** de solicitudes

### Seguridad y Acceso
- **Sesiones seguras** con Flask-Session
- **Validaciones de permisos** en todas las rutas
- **Protección CSRF** implícita en formularios
- **Acceso remoto** vía ngrok para desarrollo

### Tecnologías Utilizadas
- **Backend**: Python 3.14, Flask 3.1
- **Base de datos**: SQLite con SQLAlchemy implícito
- **Servidor**: Waitress (producción), ngrok (túnel público)
- **Frontend**: HTML5, CSS3, Bootstrap (implícito en templates)
- **Email**: smtplib con SSL
- **Autenticación 2FA**: pyotp
- **Logging**: Python logging para auditoría

## Instalación y Configuración

### Prerrequisitos
- Python 3.14+
- Cuenta de ngrok (para acceso remoto)

### Instalación
1. Clona o descarga el proyecto
2. Crea un archivo `.env` a partir de `.env.example`:
   ```bash
   copy .env.example .env
   ```
3. Ajusta los valores en `.env` según tu entorno.
4. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```
5. Ejecuta la aplicación:
   ```bash
   python app.py
   ```

### Configuración de Email y Variables de Entorno
La aplicación usa `python-dotenv` para cargar variables de entorno desde `.env`.
No es necesario editar `app.py` para configurar SMTP o la clave secreta.

Las variables disponibles son:

```text
SECRET_KEY=empresa_123
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=tu_correo@example.com
SMTP_PASSWORD=tu_app_password
EMAIL_SENDER=no-reply@tuinstitucion.cl
ESTABLECIMIENTO=Liceo Claudina Urrutia de Lavín
CODIGO_ESTABLECIMIENTO=0000
NGROK_AUTH_TOKEN=
DATABASE_URL=postgresql://usuario:contraseña@ep-endpoint.region.aws.neon.tech/neondb?sslmode=require
```

### Importar y Exportar Matrículas SIGE
- En la lista de matrículas puedes descargar una plantilla de ejemplo SIGE con el botón **Plantilla SIGE**.
- También puedes importar matrículas desde CSV usando `/import_matriculas_sige`.
- El CSV de exportación incluye `Código UTP`, `Establecimiento`, `Jornada Completa` y `Código Sector`.
- El CSV de ejemplo se llama `matriculas_sige_ejemplo.csv` y está disponible para descarga.

### Reportes PDF
- Puedes generar un reporte PDF con todos los campos de matrícula SIGE usando `/reporte_pdf/matriculas`.

### Acceso Remoto
Si configuras `NGROK_AUTH_TOKEN` en `.env`, la aplicación intentará iniciar un túnel ngrok y mostrará la URL pública cuando arranque.

## Estructura del Proyecto

```
matricula_empresa/
├── app.py                 # Aplicación principal Flask
├── database.db           # Base de datos SQLite
├── add_firewall_rule.bat # Script para abrir puerto en firewall
├── static/
│   └── img/              # Imágenes y recursos estáticos
└── templates/            # Plantillas HTML
    ├── login.html
    ├── dashboard_admin.html
    ├── dashboard_apoderado.html
    └── ... (otras plantillas)
```

## Usuarios de Prueba

- **Admin**: usuario: `admin`, contraseña: `admin123`
- **Administrativo**: usuario: `administrativo`, contraseña: `admin123`
- **Docente**: usuario: `docente`, contraseña: `admin123`
- **Apoderado**: usuario: `apoderado1`, contraseña: `admin123`

## Funcionalidades por Rol

### Administrador
- Gestión completa de usuarios
- Visualización de estadísticas globales
- Aprobación de solicitudes de informes
- Acceso a chat de soporte

### Administrativo
- Registro de matrículas
- Gestión de asistencia
- Estadísticas de matrículas y asistencia

### Docente
- Registro de asistencia
- Visualización de listas de alumnos
- Estadísticas de asistencia por alumno

### Apoderado
- Visualización de hijos matriculados
- Consulta de asistencia de sus hijos
- Solicitud de informes especiales
- Comunicación vía chat con administración

## API y Extensiones

El proyecto está estructurado para ser extensible. Futuras mejoras podrían incluir:
- API REST para integraciones
- Sistema de calificaciones
- Gestión de horarios
- Notificaciones push
- Reportes avanzados en PDF
- Backup automático de base de datos

## Seguridad

- Validación de inputs en todos los formularios
- Sanitización de datos
- Protección contra inyección SQL mediante parámetros preparados
- Sesiones con tiempo de expiración
- 2FA para cuentas críticas
- **Sistema de logging** para auditoría de acciones (app.log)

## Desarrollo

Para contribuir o modificar:
1. Asegura compatibilidad con Python 3.14+
2. Mantén la estructura de rutas y permisos
3. Actualiza este README con cambios significativos
4. Prueba todas las funcionalidades antes de commits
5. Revisa los logs en `app.log` para debugging

## Soporte

Para soporte técnico o reportes de bugs, contacta al equipo de desarrollo.

## Docker

Se incluye soporte para ejecutar la aplicación en contenedores Docker.

Construir imagen:

```bash
docker build -t matricula_empresa:latest .
```

Archivo `docker-compose.yml` incluido — levantar con:

```bash
docker compose up --build
```

Por defecto la aplicación escucha en `http://localhost:5000`.

Si quieres persistir la base de datos SQLite localmente, monta un volumen en el servicio:

```bash
docker run -p 5000:5000 -v $(pwd)/database.db:/app/database.db --env-file .env --rm matricula_empresa:latest
```

Revisa los archivos: [docker-compose.yml](docker-compose.yml) y [.env.example](.env.example)

## Despliegue en Vercel

Este proyecto cuenta con soporte oficial para desplegarse en **Vercel** usando **Serverless Functions** de Python:

1. **Subir a GitHub**: Sube este repositorio a tu cuenta de GitHub.
2. **Crear Proyecto en Vercel**: Importa el repositorio desde el panel de control de Vercel.
3. **Configurar Variables de Entorno**: En Vercel, ve a Settings -> Environment Variables y agrega `DATABASE_URL` con tu cadena de conexión de Neon, además de las credenciales de SMTP si vas a usar correos.
4. **Desplegar**: Vercel detectará el archivo `vercel.json` y compilará las dependencias en `requirements.txt` automáticamente.