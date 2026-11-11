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

- 2026-10-27: **Etapa 2 (base) en staging**: panel oscuro con menú lateral (paleta TCRC), roles Administrador /
  IT Support / Solo lectura verificados en el servidor, alta por link de invitación, login con correo, aviso de
  sesión expirada (sesión 30 min), auditoría general (accesos y usuarios), ubicaciones con tipo Hotel / Punto
  externo, migraciones automáticas al arrancar, 31 tests. Formulario público sin cambios.
  Papelera se movió a la Etapa 3 (llega con el primer borrado: tickets).

- 2026-11-05: **Etapa 2 en producción.** Incidente: caída ~6 min (502) porque `CSRF_TRUSTED_ORIGINS` de prod no
  tenía `https://` y el nuevo `migrate` al arrancar corre los checks de Django. Se corrigió la variable; además
  settings ahora agrega `https://` si falta. Respaldo previo: `.local/backup-prod-antes-etapa2-*.json`.
  Lección: antes de pasar a `main`, comparar variables de prod vs staging y correr `manage.py check --deploy`
  con los valores de prod. `pull_prod_db.py` falla si el código local tiene migraciones que prod aún no tiene
  (usar el código de `main` para respaldar).

- 2026-11-11: **Etapa 3 (tickets) en staging**: prioridad interna (Baja/Normal/Alta/Urgente), notas de resolución,
  departamento derivado del Directorio (correo → depto) o del perfil, historial con valor anterior → nuevo por campo
  (sin registros si no hubo cambios) + notas manuales, filtros por prioridad/responsable/pendientes, 6 órdenes,
  contador, limpiar filtros, paginación de 25, papelera genérica (`core/papelera.py`, la usarán los demás módulos):
  enviar a papelera Admin/IT, restaurar Admin/IT, borrado definitivo solo Admin con constancia en auditoría. 55 tests.

- 2026-11-11: **Etapas 4 y 5 (tareas + calendario) en staging**: app `tareas` (título, descripción, estado
  Pendiente/En progreso/Completada, prioridad, vence, responsable), KPIs, filtros (estado, prioridad, vencidas/hoy/
  7 días/sin fecha, responsable), 4 órdenes, cambio rápido de estado, próximos 7 días, papelera, auditoría con
  antes→después. Calendario mensual/semanal/diario/anual (Lun–Dom), detalle en un solo panel con Cerrar, crear tarea
  desde el calendario con la fecha elegida. 67 tests.

- 2026-11-11: **Etapa 6 (inventario) en staging**: app `inventario` con categorías (12 sembradas) y estados (5)
  ampliables desde la administración, ubicación = misma tabla de tickets, código automático TI-00001 o manual único
  (también contra la papelera), garantía con aviso a 90 días, estadísticas (estado, categoría, ubicación, garantías),
  búsqueda/filtros/6 órdenes/paginación, papelera y auditoría. 78 tests.

- 2026-11-11: **Etapa 7 (reportes Excel) en staging**: app `reportes` con generador único (`reportes/excel.py`,
  openpyxl): encabezado con tipo de reporte, fecha, usuario y filtros; encabezados de color, filtros de Excel, paneles
  congelados, anchos legibles, formatos de fecha/número. Exporta inventario, tickets y tareas respetando los filtros de
  cada lista (botón "Exportar a Excel"), nunca lo de la papelera; queda en auditoría. 86 tests.

### Pendiente
- [ ] Revisar `NOTIFICATION_EMAILS` en Railway: puede seguir avisando al responsable anterior.
- [ ] Correo del usuario `admin` (it@thecostaricacollection.com): confirmar quién tiene ese buzón
      (recuperación de contraseña).

### Datos de producción (26-oct)
15 tickets · 7 ubicaciones (4 hoteles + oficinas Drake, Sierpe, Uvita) · 2 usuarios.
