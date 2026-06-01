# Sistema de Tickets para Hoteles

Sistema web multi-hotel para registrar incidencias y solicitudes, con auditoría completa y dashboard de métricas.

## Características

- **Formulario público** sin login — el staff de los hoteles reporta directo desde un link.
- **Panel privado** con dashboard de KPIs, lista filtrable y detalle de cada ticket.
- **Bitácora de auditoría inmutable** — cada acción queda registrada con usuario, fecha y hora.
- **Tiempos automáticos** — creación, primera respuesta y resolución.
- **Comentarios públicos e internos** (notas privadas entre técnicos).
- **Panel admin de Django** incluido para gestión avanzada (usuarios, categorías, hoteles).
- **Multi-hotel y multi-categoría** desde el inicio.

## Stack

- Django 5
- SQLite en desarrollo (PostgreSQL en producción mediante variable `DATABASE_URL`)
- Bootstrap 5 + Bootstrap Icons (vía CDN)
- WhiteNoise para servir estáticos en producción

## Instalación local

Requiere Python 3.10 o superior.

```bash
# 1. Clonar / copiar el proyecto
cd hoteltickets

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate          # Linux/macOS
# venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables
cp .env.example .env
# Edita .env y cambia SECRET_KEY

# 5. Crear base de datos
python manage.py makemigrations tickets
python manage.py migrate

# 6. Cargar categorías y hoteles demo
python manage.py seed

# 7. Crear usuario administrador
python manage.py createsuperuser

# 8. Levantar el servidor
python manage.py runserver
```

Abre http://127.0.0.1:8000/

- `/` — formulario público para reportar tickets
- `/dashboard/` — dashboard (requiere login)
- `/tickets/` — lista filtrable
- `/admin/` — administración avanzada

## Roles sugeridos

Crea usuarios desde `/admin/` y asígnales grupos:

- **Administrador**: superusuario, ve todo.
- **Técnico**: usuario con `is_staff = True`, atiende tickets.
- **Solicitante con cuenta** (opcional): usuario normal, puede usarse si quieres autenticar al staff de los hoteles.

Para el caso típico de hoteles donde el staff reporta sin cuenta, simplemente comparte la URL pública (`/`).

## Despliegue gratis o muy barato

### Railway / Render / Fly.io

1. Sube el código a un repo de GitHub.
2. En la plataforma, crea un nuevo proyecto desde el repo.
3. Añade un servicio PostgreSQL — la plataforma genera `DATABASE_URL`.
4. Configura las variables de entorno:
   - `SECRET_KEY` — generador online o `python -c "import secrets; print(secrets.token_urlsafe(60))"`
   - `DEBUG=False`
   - `ALLOWED_HOSTS=tudominio.com,subdominio.railway.app`
5. Comando de inicio:
   ```
   python manage.py migrate && python manage.py collectstatic --no-input && gunicorn config.wsgi
   ```

Para que Django lea `DATABASE_URL` añade también `dj-database-url` a `requirements.txt`:

```
dj-database-url==2.1.0
```

## Próximos pasos sugeridos

- **Notificaciones por correo** cuando se crea o cambia un ticket.
- **Adjuntar fotos** del problema (campo `FileField`).
- **Exportar a Excel/PDF** desde el dashboard.
- **WhatsApp / Telegram** para enviar el link del formulario.
- **Códigos QR** por hotel/área (cada uno pre-llena el hotel en el form).
- **Encuesta de satisfacción** al cerrar el ticket.
- **Reportes mensuales** automáticos al correo de gerencia.

## Estructura del proyecto

```
hoteltickets/
├── config/                  # Configuración del proyecto
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── tickets/                 # App principal
│   ├── models.py            # Hotel, Categoria, Ticket, Comentario, RegistroAuditoria
│   ├── admin.py             # Admin de Django
│   ├── views.py             # Lógica de vistas
│   ├── forms.py
│   ├── urls.py
│   └── management/commands/seed.py
├── templates/               # Plantillas HTML
│   ├── base.html
│   ├── registration/login.html
│   └── tickets/
│       ├── dashboard.html
│       ├── ticket_lista.html
│       ├── ticket_detalle.html
│       ├── ticket_publico.html
│       └── ticket_confirmacion.html
├── manage.py
├── requirements.txt
└── .env.example
```
