# Guía de despliegue — Sistema de Tickets para Hoteles

Este documento te lleva paso a paso desde tu computadora hasta tener el sistema funcionando en internet con un dominio público, base de datos PostgreSQL y envío real de correos.

**Plataforma recomendada:** Railway (~$5/mes incluye todo).
**Tiempo estimado:** 30-45 minutos la primera vez.
**Costo total:** ~$5/mes en Railway + correo (gratis con Gmail o Brevo).

---

## Parte 1 — Configurar el envío de correos

Antes de desplegar, prepara las credenciales SMTP. La forma más rápida es **Gmail con app password**:

### Opción A: Gmail (recomendado para empezar)

1. Entra a tu cuenta de Google (la que usarás como remitente).
2. Ve a https://myaccount.google.com/security
3. Activa **Verificación en dos pasos** si no la tienes.
4. Ve a https://myaccount.google.com/apppasswords
5. En "Nombre de la app" pon `Tickets Hoteles` y dale Generar.
6. Google te muestra una contraseña de 16 caracteres (ejemplo: `abcd efgh ijkl mnop`). **Cópiala**, no la verás otra vez.

Anota:
- **EMAIL_HOST_USER** = tu correo `@gmail.com`
- **EMAIL_HOST_PASSWORD** = la contraseña generada (con o sin espacios, da igual)

Límite: ~500 correos al día. Suficiente para un grupo hotelero pequeño.

### Opción B: Brevo (más profesional, 300 correos/día gratis)

1. Crea cuenta en https://www.brevo.com
2. En el panel: **SMTP & API → SMTP**
3. Anota servidor, puerto, login (tu correo) y la SMTP key.

Configuración para `.env`:
```
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=tu-correo-de-registro
EMAIL_HOST_PASSWORD=tu-smtp-key
```

---

## Parte 2 — Subir el código a GitHub

Railway despliega leyendo desde un repositorio Git. Necesitas una cuenta en GitHub.

### 2.1 Instalar Git (si no lo tienes)

- **macOS**: `xcode-select --install` (instala Git automáticamente)
- **Windows**: descargar de https://git-scm.com/download/win
- **Linux**: `sudo apt install git`

Verifica: `git --version`

### 2.2 Crear cuenta y repositorio en GitHub

1. Crea cuenta en https://github.com si no tienes.
2. Clic en **+ → New repository**
3. Nombre: `hoteltickets` (o el que quieras)
4. Marca como **Private** (recomendado, contiene config sensible)
5. **NO** marques "Initialize with README"
6. Clic en **Create repository**

GitHub te muestra una página con instrucciones. Mantén esa pestaña abierta.

### 2.3 Subir tu código

Abre una terminal en la carpeta `hoteltickets/` y ejecuta:

```bash
git init
git add .
git commit -m "Versión inicial del sistema de tickets"
git branch -M main

# Reemplaza la URL con la que te muestra GitHub
git remote add origin https://github.com/TU-USUARIO/hoteltickets.git
git push -u origin main
```

Si te pide login, GitHub ya no acepta password de cuenta. Genera un **Personal Access Token**:
- https://github.com/settings/tokens → Generate new token (classic)
- Marca el scope `repo`
- Usa ese token en lugar de tu contraseña

Verifica en GitHub que ves tus archivos. **El archivo `.env` no debe aparecer** (lo bloquea `.gitignore`, está bien).

---

## Parte 3 — Desplegar en Railway

### 3.1 Crear cuenta y proyecto

1. Entra a https://railway.app
2. **Sign in with GitHub** → autoriza el acceso.
3. En el dashboard: **+ New Project → Deploy from GitHub repo**
4. Si te pide instalar Railway en GitHub, autoriza el acceso al repo `hoteltickets`.
5. Selecciona el repositorio `hoteltickets`.

Railway detecta automáticamente que es un proyecto Python y empieza a construir. **Va a fallar la primera vez** porque aún no hay base de datos ni variables. Es normal, sigue.

### 3.2 Añadir PostgreSQL

1. En el panel de tu proyecto, clic en **+ Create → Database → PostgreSQL**
2. Railway crea la base y genera automáticamente la variable `DATABASE_URL` compartida con el servicio web.

### 3.3 Configurar variables de entorno

Clic en el servicio web (el que se llama como tu repo, no el de Postgres) → pestaña **Variables**.

Agrega una a una (botón **+ New Variable**):

| Variable | Valor |
|----------|-------|
| `SECRET_KEY` | Genera con `python -c "import secrets; print(secrets.token_urlsafe(60))"` y pega el resultado |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `.up.railway.app` (con el punto al inicio, acepta todos los subdominios de Railway) |
| `CSRF_TRUSTED_ORIGINS` | `https://*.up.railway.app` |
| `SITE_URL` | (lo llenas en el paso 3.5, deja vacío por ahora) |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | `smtp.gmail.com` (o el de tu proveedor) |
| `EMAIL_PORT` | `587` |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_HOST_USER` | tu correo |
| `EMAIL_HOST_PASSWORD` | tu app password |
| `DEFAULT_FROM_EMAIL` | `Tickets Hoteles <tucorreo@gmail.com>` |
| `NOTIFICATION_EMAILS` | correos que recibirán alerta, separados por coma |

> **Importante:** `DATABASE_URL` aparece sola si añadiste PostgreSQL al proyecto, no la dupliques manualmente.

### 3.4 Forzar redespliegue

Pestaña **Deployments** → menú de los tres puntos en el último deploy → **Redeploy**.

Mira los logs en tiempo real. Cuando termine sin errores, verás algo como `Listening on 0.0.0.0:8080`.

### 3.5 Obtener tu dominio público

Pestaña **Settings → Networking → Generate Domain**.

Railway te da algo tipo: `hoteltickets-production.up.railway.app`

Cópialo y:
- Vuelve a **Variables**
- Edita `SITE_URL` poniendo `https://hoteltickets-production.up.railway.app` (con tu URL real)
- Edita `ALLOWED_HOSTS` poniendo el hostname exacto: `hoteltickets-production.up.railway.app`

Redespliega de nuevo.

### 3.6 Crear el usuario administrador en producción

Railway tiene una **CLI** o puedes usar la terminal web.

**Opción 1: Terminal en el navegador**
- En tu servicio: pestaña **Deployments → último deploy → ⋮ → View Logs**
- Hay un botón de **Shell** o **Terminal** en la parte superior
- Ejecuta:
```bash
python manage.py createsuperuser
python manage.py seed
```

**Opción 2: Instalar Railway CLI** (recomendado)
```bash
# macOS / Linux
brew install railway
# o
curl -fsSL https://railway.app/install.sh | sh

# Windows: descargar de https://docs.railway.app/cli
```

Luego:
```bash
railway login
railway link    # selecciona tu proyecto
railway run python manage.py createsuperuser
railway run python manage.py seed
```

---

## Parte 4 — Verificar y compartir

1. Abre `https://tu-dominio.up.railway.app/` en el navegador.
2. Deberías ver el formulario público.
3. Crea un ticket de prueba con tu propio correo como solicitante.
4. **Revisa tu bandeja de entrada**: deberías recibir el correo de confirmación.
5. Si configuraste `NOTIFICATION_EMAILS`, esos correos también reciben la alerta.
6. Inicia sesión en `/admin/` con el superuser que creaste y elimina/edita los hoteles demo, agrega los reales.

**Comparte estos enlaces con los hoteles:**
- `https://tu-dominio.up.railway.app/` — para reportar tickets
- `https://tu-dominio.up.railway.app/dashboard/` — para tu equipo (requiere login)

---

## Parte 5 — Dominio propio (opcional)

Si quieres una URL personalizada tipo `tickets.tuempresa.com`:

1. Compra un dominio si no tienes (Namecheap, Cloudflare Registrar son baratos).
2. En Railway: **Settings → Networking → Custom Domain → Add Domain**
3. Pon tu subdominio (ej. `tickets.tuempresa.com`)
4. Railway te da un valor CNAME.
5. En tu proveedor de DNS, crea un registro CNAME apuntando a ese valor.
6. Espera 5-30 minutos a que propague. Railway emite el certificado HTTPS automáticamente.
7. Actualiza `SITE_URL`, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` en las variables con el nuevo dominio.

---

## Actualizar el sistema después

Cuando hagas cambios al código local:

```bash
git add .
git commit -m "describe lo que cambió"
git push
```

Railway detecta el push y redespliega automáticamente. Toma 1-2 minutos.

---

## Costos esperados

- **Railway**: el primer $5 son trial. Después ~$5-10/mes según uso. Para este sistema con tráfico de varios hoteles está dentro del rango bajo.
- **Gmail SMTP**: gratis hasta ~500 correos/día.
- **Brevo**: gratis hasta 300 correos/día.
- **Dominio propio**: ~$10-15/año.

Total mensual realista: **$5-10**.

---

## Problemas comunes

**Build falla con "ModuleNotFoundError"**
Falta una librería en `requirements.txt`. Añádela, haz commit, push.

**Error 500 al abrir el sitio**
Revisa los logs en Railway. Casi siempre es `ALLOWED_HOSTS` mal configurado.

**Los correos no llegan**
- Revisa la carpeta de spam la primera vez.
- Verifica las credenciales SMTP en Variables.
- Mira los logs del deploy: cualquier error de envío aparece como `Error enviando correo`.

**Para Gmail: "Authentication failed"**
La app password debe ser exacta y la cuenta debe tener 2FA activada.

**"CSRF verification failed" al hacer login**
Falta el dominio en `CSRF_TRUSTED_ORIGINS`. Añádelo con `https://` al inicio.

---

¿Algo no salió como esperabas? Comparte el error y te ayudo a resolverlo.
