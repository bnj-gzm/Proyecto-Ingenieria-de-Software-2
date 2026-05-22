# Proyecto Semestral - Ingeniería de Software

Aplicación web desarrollada con un enfoque centrado en la simplicidad, velocidad y fiabilidad, utilizando renderizado del lado del servidor e interactividad moderna.

## 🛠️ Stack Tecnológico
* **Backend:** Python + FastAPI
* **Frontend:** HTML/Jinja2 + HTMX + Tailwind CSS
* **Base de Datos:** PostgreSQL / Neon
* **Autenticación:** JWT firmado en cookie HttpOnly + protección CSRF en formularios

## Roles
* **Admin:** gestiona usuarios y asigna roles desde `/admin/usuarios`.
* **Supervisor:** revisa ARTs desde `/supervisor/art`.
* **Usuario:** crea ARTs y ve sus propios registros.

## Flujo ART
1. Un usuario crea una ART y la asigna a un trabajador registrado.
2. La ART se deriva a un supervisor real del sistema.
3. El supervisor marca la ART como `aprobada`, `rechazada`, `corregir` o `pendiente`.
4. La revisión queda guardada con comentario, responsable y fecha.

## 🚀 Configuración del Entorno Local

1. **Clonar el repositorio:**
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd <NOMBRE_DE_LA_CARPETA>
   ```

2. **Configurar variables de entorno:**
   ```bash
   cp .env.example .env
   ```

   Edita `.env` con tu conexión de Neon y una `SECRET_KEY` larga y aleatoria.

3. **Instalar dependencias y ejecutar:**
   ```bash
   pip install -r requirements.txt
   uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
   ```
