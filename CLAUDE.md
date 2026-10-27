# CLAUDE.md — Hotel Tickets (TCRC)

Sistema de tickets de TI para los hoteles y oficinas del grupo, en camino a **plataforma integral de gestión
de TI**: el plan aprobado por etapas y las decisiones del Controller están en `docs/AUDITORIA_Y_PLAN.md`
(leer antes de construir). Leé también `PROGRESS.md` (estado y pendientes) y `README.md` (estructura).
Dos zonas: formulario público sencillo (no se toca) y backstage de IT (tema oscuro, menú lateral).
Cada etapa: staging → pruebas → aprobación del Controller → producción. Producción: https://tickets.thecostaricacollection.com

## Dónde vive
- **Repo:** `ITCRC1/hoteltickets` (rama `main`). Nunca en brodriguez7301-dot.
- **Railway:** workspace *Proyectos TCRC* → proyecto **Tickets** → servicios `Tickets` (Django) + `Postgres`.
- **Deploy = `git push` a `main`.** Railway construye desde GitHub automáticamente (Railpack, Python 3.12).
  `Procfile` corre `migrate` + `collectstatic` en el release.

## Ambientes (desde 2026-10-27)
| Ambiente | Rama | URL | Base | Correos |
|---|---|---|---|---|
| **production** | `main` | https://tickets.thecostaricacollection.com | Postgres prod | reales (Brevo) |
| **staging** | `staging` | https://tickets-staging-bafe.up.railway.app | Postgres propio (copia de prod) | **apagados** (consola) |

- **Flujo:** trabajar en la rama `staging` → `git push` → se publica solo en staging → probar →
  cuando el Controller lo apruebe, merge `staging` → `main` y push (= producción).
- Staging tiene correos apagados a propósito: la copia trae correos reales de solicitantes.
- Refrescar staging con datos de prod: `scripts\copy_prod_to_staging.py` (solo lee prod; reemplaza staging).
- Los scripts siempre pasan `-e production` / `-e staging` explícito; no dependen de `railway link`.

## Roles y acceso (Etapa 2)
- `core/roles.py`: **Administrador** (todo; = superusuario, entra al admin técnico), **IT Support** (atiende,
  no administra), **Solo lectura**. Verificar SIEMPRE en la vista con `@roles.requiere_rol(...)` /
  `roles.puede_editar()`; ocultar botones no basta. Sin rol → 403.
- Alta por **invitación** (`core/invitaciones.py`, igual que Owner Dashboard): link de un solo uso, 7 días, solo
  se guarda la huella SHA-256. El admin nunca escribe contraseñas ajenas.
- Login con usuario o correo (`core/backends.py`); aviso de sesión expirada vía cookie `tk_sesion`.
- Auditoría general: `core.auditoria.auditar(request, ACCION, modulo, objeto, cambios={campo: [antes, después]})`.
- Plantillas: `base.html` = backstage (oscuro, menú lateral, CSS en `core/static/core/plataforma.css`);
  `base_publico.html` = formulario público (no tocar); `base_auth.html` = login/invitación.

## Stack
Django 5.0 · python-decouple (`.env`) · dj-database-url · gunicorn · whitenoise · django-anymail (Brevo).
Sin `DATABASE_URL` usa SQLite (`db.sqlite3`); en Railway usa Postgres.

## Reglas
- **Local ≠ producción.** El `/admin` local (`127.0.0.1:8001`) solo cambia `db.sqlite3`. El `/admin` de
  producción cambia datos reales al instante. El código llega a producción solo con `git push`.
- **Producción ya está migrada:** nunca editar migraciones existentes; siempre una nueva incremental
  (`makemigrations`), probada en local contra una copia de producción antes del push.
- **Nunca versionar datos reales ni secretos:** `.env`, `db.sqlite3`, `.local/` (copias de prod) están fuera de git.
- El formulario público (`/`) no requiere login; todo lo demás sí (`@login_required`).
- Toda acción sobre un ticket queda en `RegistroAuditoria` (bitácora inmutable): mantenerlo en cambios nuevos.
- Correos: avisos de ticket nuevo van a `NOTIFICATION_EMAILS` (variable en Railway), no a los usuarios.
- El usuario usa **Windows PowerShell 5.1**: comandos sin `&&` (usar `;`), rutas `C:\…`, `.\venv\Scripts\python.exe`.

## Comandos (PowerShell, desde `C:\dev\hoteltickets`)
- Levantar local: `start-local.cmd` (o `.\venv\Scripts\python.exe manage.py runserver 8001`) → http://127.0.0.1:8001
  (el 8000 lo usa otro proyecto).
- Copiar producción → local: `.\venv\Scripts\python.exe scripts\pull_prod_db.py` (solo lee prod; reemplaza
  `db.sqlite3`, respaldo en `.local/`).
- Comando contra producción: `.\venv\Scripts\python.exe scripts\prod_manage.py <comando>` (pide escribir PROD);
  contra staging: `scripts\prod_manage.py --staging <comando>` (pide STAGING).
- **Migraciones:** Railway no corre `release:` (es de Heroku); por eso el `web:` del Procfile hace `migrate` al
  arrancar (desde la Etapa 2). Probar siempre la migración en staging antes de pasar a `main`.
- Tests: `.env\Scripts\python.exe manage.py test` (con `DATABASE_URL` vacío → SQLite).
- Migración nueva: `.\venv\Scripts\python.exe manage.py makemigrations tickets`
- Railway CLI: lo instaló la app de Claude en su AppData virtualizado, el PowerShell del usuario no lo ve;
  los scripts lo encuentran solos.
