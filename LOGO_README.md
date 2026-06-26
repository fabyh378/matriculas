# Logo del Liceo Claudina Urrutia de Lavín

## Información del Logo

Se ha integrado el logo oficial del Liceo Claudina Urrutia de Lavín en el sistema de gestión educativa.

### Ubicación del Logo
- **Archivo SVG**: `static/img/logo_liceo.svg`
- **Ubicaciones de uso**:
  - Barra de navegación principal (base.html)
  - Página de login (login.html)
  - Dashboard de Docente (dashboard_docente.html)
  - Dashboard de Administrador (dashboard_admin.html)
  - Dashboard Administrativo (dashboard_administrativo.html)

### Características del Logo
- **Formato**: SVG (escalable vectorial)
- **Colores principales**:
  - Azul institucional: #1e3a8a
  - Azul secundario: #3b82f6
  - Blanco: #ffffff
- **Elementos**:
  - Nombre completo del liceo
  - Icono de libro/educación
  - Gradientes modernos
  - Texto descriptivo

### Implementación Técnica
- El logo se sirve como archivo estático de Flask
- Configurado en `app.py` con `static_folder='static'`
- Accesible vía `url_for('static', filename='img/logo_liceo.svg')` en templates Jinja2
- O vía `/static/img/logo_liceo.svg` en archivos HTML independientes

### Uso en Templates
```html
<img src="{{ url_for('static', filename='img/logo_liceo.svg') }}"
     alt="Logo Liceo Claudina Urrutia de Lavín"
     style="height: 60px;">
```

## Notas Importantes
- El logo actual es una representación gráfica creada específicamente para este sistema
- Para usar el logo oficial real del liceo, contactar con la institución educativa
- El diseño mantiene la identidad institucional con colores y elementos representativos