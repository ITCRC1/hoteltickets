# PROGRESS — Hotel Tickets

## ▶ Retomar aquí (2026-10-26)
Proyecto tomado por el Controller (fincontroller@seedcostarica.com) tras la salida del responsable anterior de TI.

### Hecho
- Clonado en `C:\dev\hoteltickets`, venv + `.env` local (SQLite, correo a consola), `railway link` al proyecto Tickets.
- `scripts/pull_prod_db.py` (copia prod → local) y `scripts/prod_manage.py` (manage.py contra prod).
- Superusuarios en producción: `admin` (it@thecostaricacollection.com, clave cambiada por el Controller) y
  `fincontroller@seedcostarica.com`. Se conservan ambos.
- Estructura de trabajo igual a los demás proyectos: `CLAUDE.md`, `PROGRESS.md`, `.claude/launch.json`,
  `start-local.cmd`, `.railwayignore`.

- 2026-10-27: ambiente **staging** en Railway (rama `staging`, base propia con copia de prod, correos apagados):
  https://tickets-staging-bafe.up.railway.app — producción intacta.

### Pendiente
- [ ] Revisar `NOTIFICATION_EMAILS` en Railway: puede seguir avisando al responsable anterior.
- [ ] Correo del usuario `admin` (it@thecostaricacollection.com): confirmar quién tiene ese buzón
      (recuperación de contraseña).
- [ ] No hay tests automáticos.

### Datos de producción (26-oct)
15 tickets · 7 ubicaciones (4 hoteles + oficinas Drake, Sierpe, Uvita) · 2 usuarios.
