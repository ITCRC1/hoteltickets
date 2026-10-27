# Plataforma de Gestión de TI — Auditoría y Plan (Etapa 1)

*2026-10-27 · Base: `ITCRC1/hoteltickets` · Trabajo en ambiente **staging**; producción intacta hasta aprobación.*

---

## 1. Diagnóstico técnico

| Aspecto | Estado actual |
|---|---|
| Stack | Django 5.0 (Python 3.12), plantillas HTML server-side + Bootstrap 5 (CDN). Monolito: backend y pantallas en la misma app. |
| Base de datos | PostgreSQL en Railway (prod y staging separados); SQLite en local. 6 migraciones aplicadas. |
| Tamaño | ~1,560 líneas (1 app `tickets`: 5 modelos, 5 vistas, 3 formularios, 8 plantillas). 34 commits desde 2026-06-01. |
| Autenticación | Login estándar de Django (hash PBKDF2), `@login_required` en vistas privadas, logout por POST, CSRF activo. |
| Autorización | **No existe.** Todo usuario con login ve y modifica todo. Grupos de Django desactivados en el admin. |
| Correo | Brevo (API) con respaldo SMTP; destinatarios internos por variable `NOTIFICATION_EMAILS`. |
| Despliegue | Railway: push a `main` → producción; push a `staging` → staging. **Railway no ejecuta `release:` del Procfile → migraciones manuales.** |
| Pruebas | **Ninguna.** |
| Datos en producción | 15 tickets, 7 ubicaciones, 1 categoría, 2 usuarios. |

### Modelos existentes
- **Hotel** (= ubicación): nombre, ubicación, oficina, contacto, teléfono, activo.
- **Categoria**: nombre, descripción, color, activa.
- **Ticket**: título, descripción, hotel, categoría, ubicación específica, estado (5), solicitante (nombre + correo), asignado_a, fechas de creación / actualización / primera respuesta / resolución / cierre.
- **Comentario**: ticket, autor, contenido, interno (sí/no).
- **RegistroAuditoria**: ticket, usuario, acción, detalle (texto libre), fecha. Inmutable.

---

## 2. Qué ya existe (por módulo solicitado)

| # | Módulo | Estado | Qué hay hoy | Qué falta |
|---|---|---|---|---|
| 1 | Autenticación | 🟡 | Login, logout, rutas protegidas, hash seguro, sesión por inactividad (corregida en staging: 30 min) | Login por **correo** además de usuario; aviso claro de "sesión expirada"; registro de accesos |
| 2 | Dashboard | 🟡 | KPIs de tickets: totales, por estado, por hotel, por categoría, recientes, tiempo de resolución | KPIs de tareas, inventario, presupuesto, suscripciones; accesos directos |
| 3 | Tareas | 🆕 | — | Todo |
| 4 | Calendario | 🆕 | — | Vistas mensual / semanal / diaria / anual |
| 5 | Tickets | 🟡 **(lo más avanzado)** | Formulario público, lista con filtros (estado, hotel, categoría, texto), detalle, cambio de estado, asignación, comentarios públicos/internos, correos, bitácora | **Prioridad** (existió y se eliminó el 2026-06-10), filtro y orden por responsable/prioridad, contador de resultados, limpiar filtros, notas de resolución, historial con **valor anterior → nuevo**, eliminación desde la interfaz, paginación (hoy tope de 200) |
| 6 | Inventario | 🆕 | — | Todo (activos, categorías, estados ampliables, estadísticas) |
| 7 | Reportes / Excel | 🆕 | — | Exportación de inventario, tickets y tareas (librería `openpyxl`) |
| 8 | Presupuestos | 🆕 | — | Presupuesto anual por categoría, gastos, CRC/USD con tipo de cambio, indicadores |
| 9 | Suscripciones | 🆕 | — | Todo |
| 10 | Usuarios | 🟡 | Solo desde el admin técnico de Django | Pantalla propia: crear, activar/desactivar, asignar rol |
| 11 | Roles y permisos | 🆕 | — | Administrador y Solo lectura, verificados en backend |
| 12 | Asistente IA | 🆕 | — | Todo |
| 13 | Configuración | 🟡 | Admin técnico de Django; correos en variables de Railway | Pantalla propia: categorías, monedas, tipos de cambio, destinatarios de avisos, parámetros |
| 14 | Auditoría | 🟡 | Solo para tickets, texto libre | Auditoría general de todos los módulos (quién, qué, antes/después, cuándo) |

**Se conserva sin cambios:** el formulario público de reporte (vista sencilla para quien reporta), los correos, la bitácora de tickets y los datos existentes.

---

## 3. Problemas detectados

1. **Sin roles:** cualquier usuario con login puede modificar cualquier ticket y ve el enlace a Administración.
2. **Sesión de 60 segundos** — *ya corregido en staging (30 min, configurable).*
3. **Migraciones no automáticas en Railway:** el `release:` del Procfile se ignora. Riesgo de que una versión nueva arranque sin sus tablas. → Propuesta: correr `migrate` al arrancar el servicio.
4. **"Asignar a" lista a todos los usuarios**, no solo a técnicos.
5. **La prioridad fue eliminada** de los tickets en junio; el nuevo requerimiento la pide. Hay que confirmar si se reintroduce (solo en la vista interna).
6. **Historial sin valor anterior/nuevo**: hoy guarda solo un texto.
7. **Eliminación solo desde el admin técnico**, sin papelera ni confirmación propia.
8. **Sin pruebas automáticas.**
9. **Destinatarios de avisos fuera de la app** (variable en Railway): posiblemente aún apuntan al responsable anterior.
10. **Tema claro** en el panel; el requerimiento pide tema oscuro con menú lateral.

---

## 4. Propuesta de arquitectura

**Mantener Django.** Cubre todo lo pedido (autenticación, permisos, ORM, migraciones, admin) y ya está en producción; cambiar de tecnología no aporta y agrega riesgo.

```
config/            ajustes, urls
core/      (nuevo) layout oscuro con menú lateral, roles/permisos, auditoría general,
                   papelera (borrado lógico), configuración, usuarios, monedas y tipos de cambio
tickets/   (existe) se amplía: prioridad, notas de resolución, historial antes→después, filtros
tareas/    (nuevo) tareas + calendario (4 vistas)
inventario/(nuevo) activos, categorías y estados configurables
finanzas/  (nuevo) presupuestos anuales, gastos, suscripciones
reportes/  (nuevo) exportaciones a Excel
asistente/ (nuevo) chat de IA con herramientas de solo lectura y acciones con confirmación
```

- **Dos zonas:** *pública* (formulario actual, sin cambios visuales) y *backstage IT* (menú lateral oscuro con un tab por módulo).
- **Roles con Grupos y Permisos de Django**, verificados en cada vista (no solo ocultando botones). Ampliable a más roles.
- **Borrado lógico** (papelera recuperable) + borrado definitivo solo para Administrador.
- **Auditoría general**: un registro único para todos los módulos (usuario, acción, registro, valores antes/después, fecha).
- **Dinero**: `Decimal` con 2 decimales; cada monto guarda su moneda original; las conversiones usan una tabla de tipos de cambio registrados (nunca se suman CRC + USD sin convertir).
- **IA**: el asistente usa herramientas que leen la base **con los permisos del usuario**; las acciones que modifican piden confirmación. La clave API vive en variables de Railway, nunca en el código.
- **Migraciones automáticas** al arrancar el servicio, para que Railway nunca quede con la base desfasada.

---

## 5. Plan de implementación, prioridades y estimación

Cada etapa: se construye en staging → pruebas automáticas → tú revisas → apruebas → pasa a producción.
Estimación en **sesiones de trabajo** (una sesión ≈ medio día).

| Etapa | Contenido | Prioridad | Estimación |
|---|---|---|---|
| 1 | Auditoría (este documento) | — | ✅ |
| 2 | Base: layout oscuro + menú lateral, roles Admin/Solo lectura, login por correo, sesión expirada, migraciones automáticas, auditoría general, papelera | **Alta** — todo lo demás se apoya aquí | 2–3 |
| 3 | Tickets: prioridad, notas de resolución, filtros/orden/contador, historial antes→después, eliminar con papelera, paginación | **Alta** — es lo que se usa hoy | 1–2 |
| 4 | Tareas | Alta | 1 |
| 5 | Calendario (mensual, semanal, diaria, anual) | Media | 1–2 |
| 6 | Inventario | Alta | 1–2 |
| 7 | Reportes Excel (inventario, tickets, tareas) | Media | 1 |
| 8 | Dashboard integral (todos los módulos) | Media — conviene después de tener datos | 1 |
| 9 | Presupuestos + gastos + monedas | Media | 2 |
| 10 | Suscripciones + proyecciones | Media | 1 |
| 11 | Asistente IA (general + datos internos + acciones con confirmación) | Media | 2–3 |
| 12 | Configuración y usuarios desde la interfaz | Media | 1 |
| 13 | Pruebas finales, respaldo, paso a producción | Alta | 1 |
| | **Total aproximado** | | **15–21 sesiones** |

*Cambio respecto al orden del documento:* el Dashboard integral va después de los módulos que alimenta, para no mostrar indicadores vacíos.

---

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Alcance grande sobre una base pequeña | Etapas cortas, cada una aprobada antes de seguir |
| Migraciones en producción | Probar siempre en staging con copia de datos; respaldo antes de cada paso a producción |
| Datos personales en staging (correos reales) | Correos apagados en staging (ya hecho) |
| Costo y privacidad de la IA | Comparación de proveedores antes de la etapa 11; sin contratar ni configurar claves sin autorización |
| Un solo administrador con acceso | Mantener 2 superusuarios (ya hecho) |

---

## 7. Decisiones del Controller (2026-10-27)

1. **Roles: tres.** *Administrador* (todo), **IT Support** (atiende tickets, tareas, inventario; no borra
   definitivo ni configura), *Solo lectura*.
2. **Prioridad de tickets: se reintroduce solo en la vista interna.** El formulario público no cambia.
3. **Formulario público: se queda igual.** El *departamento* no se pregunta; se **deriva** del directorio
   (correo del solicitante → departamento) que se llena al crear el usuario/contacto.
4. **Ubicaciones:** 4 hoteles + **puntos estratégicos fuera del hotel** que requieren control (oficinas
   Drake, Sierpe, Uvita y otros). Una sola tabla de ubicaciones, con *tipo* (Hotel / Punto externo),
   compartida por tickets e inventario.
5. **Tipo de cambio: manual, uno por mes.** Tabla mensual de validación (año, mes, CRC por USD). Todo
   monto en otra moneda se convierte con el tipo del mes de su fecha; sin tipo registrado → aviso visible,
   no se convierte en silencio.
6. **Año presupuestario: enero–diciembre.**
7. **IA: solo Claude (Anthropic).** Sin comparación de proveedores. El asistente dentro de la app usa la
   API de Anthropic con su propia clave (variable en Railway) y costo por uso; se configura en la etapa 11
   con autorización.
8. **Alta de usuarios por invitación (igual que Owner Dashboard y Hotel Consolidation).** El admin
   crea el usuario (correo, nombre, rol) → la app genera un **link de un solo uso, válido 7 días**, que
   se muestra una sola vez con botón *Copiar* → el admin lo envía por el medio que quiera → la persona
   abre el link, define su contraseña (10+ caracteres, letras y números, distinta del correo) y entra.
   Botón **"Link de invitación"** en cada usuario para generar uno nuevo (quien no entró u olvidó su
   clave); el anterior deja de servir. En la base solo se guarda la huella SHA-256 del token. Lista de
   usuarios con estado *invitación pendiente* / último ingreso. Auditoría: INVITAR y ACEPTAR_INVITACIÓN.
   El admin nunca conoce ni escribe contraseñas ajenas.
