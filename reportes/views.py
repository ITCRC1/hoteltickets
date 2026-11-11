"""
Reportes y exportaciones a Excel. Cada exportación usa los mismos filtros que la lista de su módulo
(lo que ves es lo que se exporta) y deja constancia en la auditoría. Los tres roles pueden exportar;
lo que está en la papelera nunca se exporta.
"""
from django.contrib.auth.models import User
from django.shortcuts import render

from core import roles
from inventario import views as inventario_views
from inventario.models import Activo, CategoriaActivo, EstadoActivo
from tareas import views as tareas_views
from tareas.models import Tarea
from tickets import views as tickets_views
from tickets.models import Categoria, Hotel, Ticket

from .excel import Columna, respuesta_excel


def _nombre(u):
    return (u.get_full_name() or u.username) if u else ''


def _por_pk(modelo, valor):
    return str(modelo.objects.filter(pk=valor).first() or valor) if str(valor).isdigit() else valor


def _describir(f, etiquetas, catalogos=None):
    """Convierte los filtros activos en texto legible para el encabezado del Excel."""
    catalogos = catalogos or {}
    salida = []
    for clave, etiqueta in etiquetas.items():
        valor = f.get(clave)
        if not valor:
            continue
        if clave in catalogos:
            valor = catalogos[clave](valor)
        salida.append(f'{etiqueta}: {valor}')
    return salida


@roles.requiere_rol()
def reportes(request):
    from finanzas.models import Gasto, Suscripcion
    return render(request, 'reportes/index.html', {
        'conteos': {'inventario': Activo.objects.count(), 'tickets': Ticket.objects.count(), 'tareas': Tarea.objects.count(),
                    'gastos': Gasto.objects.count(), 'suscripciones': Suscripcion.objects.count()},
    })


@roles.requiere_rol()
def exportar_inventario(request):
    qs, f = inventario_views.filtrar(request)
    columnas = [Columna('Código', 12), Columna('Equipo', 30), Columna('Categoría', 16), Columna('Marca', 14),
                Columna('Modelo', 18), Columna('Número de serie', 20), Columna('Ubicación', 26),
                Columna('Departamento', 18), Columna('Responsable', 20), Columna('Estado', 14),
                Columna('Adquisición', 13, 'fecha'), Columna('Garantía hasta', 14, 'fecha'),
                Columna('Observaciones', 40)]
    filas = ([a.codigo, a.nombre, str(a.categoria), a.marca, a.modelo, a.numero_serie, str(a.ubicacion),
              a.departamento, a.responsable, str(a.estado), a.fecha_adquisicion, a.garantia_hasta, a.observaciones]
             for a in qs)
    filtros = _describir(f, {'q': 'Búsqueda', 'categoria': 'Categoría', 'estado': 'Estado', 'ubicacion': 'Ubicación',
                             'departamento': 'Departamento', 'garantia': 'Garantía'},
                         {'categoria': lambda v: _por_pk(CategoriaActivo, v), 'estado': lambda v: _por_pk(EstadoActivo, v),
                          'ubicacion': lambda v: _por_pk(Hotel, v),
                          'garantia': lambda v: {'vencida': 'vencida', 'por_vencer': 'por vencer', 'sin': 'sin registrar'}.get(v, v)})
    return respuesta_excel('Inventario', columnas, filas, request, filtros)


@roles.requiere_rol()
def exportar_tickets(request):
    qs, f = tickets_views.filtrar(request)
    columnas = [Columna('#', 7, 'entero'), Columna('Título', 32), Columna('Ubicación', 26), Columna('Departamento', 16),
                Columna('Categoría', 16), Columna('Prioridad', 11), Columna('Estado', 13), Columna('Responsable', 20),
                Columna('Solicitante', 20), Columna('Correo solicitante', 26), Columna('Creado', 17, 'fechahora'),
                Columna('Primera respuesta', 17, 'fechahora'), Columna('Resuelto', 17, 'fechahora'),
                Columna('Cerrado', 17, 'fechahora'), Columna('Descripción', 45), Columna('Notas de resolución', 45)]
    filas = ([t.pk, t.titulo, str(t.hotel), t.departamento, str(t.categoria), t.get_prioridad_display(),
              t.get_estado_display(), _nombre(t.asignado_a), t.solicitante_nombre, t.solicitante_email, t.creado_en,
              t.primera_respuesta_en, t.resuelto_en, t.cerrado_en, t.descripcion, t.notas_resolucion] for t in qs)
    filtros = _describir(f, {'q': 'Búsqueda', 'estado': 'Estado', 'prioridad': 'Prioridad', 'hotel': 'Ubicación',
                             'categoria': 'Categoría', 'asignado': 'Responsable'},
                         {'estado': lambda v: 'pendientes' if v == 'abiertos' else dict(Ticket.ESTADO_CHOICES).get(v, v),
                          'prioridad': lambda v: dict(Ticket.PRIORIDAD_CHOICES).get(v, v),
                          'hotel': lambda v: _por_pk(Hotel, v), 'categoria': lambda v: _por_pk(Categoria, v),
                          'asignado': lambda v: 'sin asignar' if v == 'ninguno' else _nombre(User.objects.filter(pk=v).first()) if v.isdigit() else v})
    return respuesta_excel('Tickets', columnas, filas, request, filtros)


@roles.requiere_rol()
def exportar_tareas(request):
    qs, f = tareas_views.filtrar(request)
    columnas = [Columna('Tarea', 32), Columna('Estado', 13), Columna('Prioridad', 11), Columna('Vence', 12, 'fecha'),
                Columna('Responsable', 20), Columna('Creada', 17, 'fechahora'), Columna('Completada', 17, 'fechahora'),
                Columna('Descripción', 50)]
    filas = ([t.titulo, t.get_estado_display(), t.get_prioridad_display(), t.fecha_vencimiento, _nombre(t.responsable),
              t.creado_en, t.completada_en, t.descripcion] for t in qs)
    filtros = _describir(f, {'q': 'Búsqueda', 'estado': 'Estado', 'prioridad': 'Prioridad', 'vence': 'Vencimiento',
                             'responsable': 'Responsable'},
                         {'estado': lambda v: 'no completadas' if v == 'abiertas' else dict(Tarea.ESTADO_CHOICES).get(v, v),
                          'prioridad': lambda v: dict(Tarea.PRIORIDAD_CHOICES).get(v, v),
                          'vence': lambda v: {'vencidas': 'vencidas', 'hoy': 'hoy', 'semana': 'próximos 7 días', 'sin_fecha': 'sin fecha'}.get(v, v),
                          'responsable': lambda v: 'sin responsable' if v == 'ninguno' else _nombre(User.objects.filter(pk=v).first()) if v.isdigit() else v})
    return respuesta_excel('Tareas', columnas, filas, request, filtros)


@roles.requiere_rol()
def exportar_presupuesto(request):
    from django.utils import timezone

    from finanzas.calculos import resumen_anual
    from finanzas.models import CRC, USD
    hoy = timezone.localdate()
    valor = request.GET.get('anio', '')
    anio = int(valor) if valor.isdigit() else hoy.year
    moneda = CRC if request.GET.get('moneda') == CRC else USD
    r = resumen_anual(anio, moneda, hoy)
    columnas = [Columna('Categoría', 26), Columna(f'Asignado ({moneda})', 16, 'dinero'), Columna(f'Utilizado ({moneda})', 16, 'dinero'),
                Columna(f'Pagado ({moneda})', 16, 'dinero'), Columna(f'Pendiente ({moneda})', 16, 'dinero'),
                Columna(f'Disponible ({moneda})', 16, 'dinero'), Columna('Ejecución', 11, 'porcentaje'),
                Columna(f'Proyección cierre ({moneda})', 18, 'dinero'), Columna(f'Suscripciones ({moneda})', 16, 'dinero')]
    filas = [[str(c['categoria']), c['asignado'], c['utilizado'], c['pagado'], c['pendiente'], c['disponible'],
              (c['ejecucion'] / 100) if c['ejecucion'] is not None else None, c['proyeccion'], c['suscripciones']]
             for c in r['categorias']]
    t = r['total']
    filas.append(['TOTAL', t['asignado'], t['utilizado'], t['pagado'], t['pendiente'], t['disponible'],
                  (t['ejecucion'] / 100) if t['ejecucion'] is not None else None, t['proyeccion'], t['suscripciones']])
    filtros = [f'Año: {anio}', f'Moneda: {moneda}']
    if r['sin_tipo'] or r['presupuesto_sin_tipo']:
        filtros.append(f'ATENCIÓN: {len(r["sin_tipo"])} gastos y {len(r["presupuesto_sin_tipo"])} presupuestos '
                       f'sin tipo de cambio NO incluidos')
    return respuesta_excel(f'Presupuesto {anio}', columnas, filas, request, filtros, nombre=f'presupuesto_{anio}_{moneda}.xlsx')


@roles.requiere_rol()
def exportar_gastos(request):
    from finanzas.models import CategoriaGasto, Gasto
    from finanzas.views import filtrar_gastos
    qs, f = filtrar_gastos(request)
    columnas = [Columna('Fecha', 12, 'fecha'), Columna('Concepto', 34), Columna('Categoría', 20), Columna('Proveedor', 20),
                Columna('Monto', 14, 'dinero'), Columna('Moneda', 8), Columna('Tipo de cambio del mes', 14),
                Columna('Monto USD', 14, 'dinero'), Columna('Monto CRC', 16, 'dinero'), Columna('Estado', 16),
                Columna('Presupuesto', 12), Columna('Observaciones', 34)]
    filas = ([g.fecha, g.concepto, str(g.categoria), g.proveedor, g.monto, g.moneda,
              g.tipo_cambio if g.tipo_cambio else 'sin registrar', g.monto_en('USD'), g.monto_en('CRC'),
              g.get_estado_display(), g.presupuesto.anio if g.presupuesto else 'sin presupuesto', g.observaciones]
             for g in qs)
    filtros = _describir(f, {'q': 'Búsqueda', 'anio': 'Año', 'mes': 'Mes', 'categoria': 'Categoría', 'estado': 'Estado',
                             'moneda': 'Moneda'},
                         {'categoria': lambda v: _por_pk(CategoriaGasto, v),
                          'estado': lambda v: dict(Gasto.ESTADO_CHOICES).get(v, v)})
    return respuesta_excel('Gastos', columnas, filas, request, filtros)


@roles.requiere_rol()
def exportar_suscripciones(request):
    from finanzas.views import filtrar_suscripciones
    qs, f = filtrar_suscripciones(request)
    columnas = [Columna('Servicio', 28), Columna('Proveedor', 20), Columna('Categoría', 20),
                Columna('Costo por período', 16, 'dinero'), Columna('Moneda', 8), Columna('Frecuencia', 12),
                Columna('Costo mensual', 14, 'dinero'), Columna('Costo anual', 14, 'dinero'), Columna('Inicio', 12, 'fecha'),
                Columna('Próxima renovación', 14, 'fecha'), Columna('Estado', 11), Columna('Responsable', 20),
                Columna('Descripción', 34)]
    filas = ([s.nombre, s.proveedor, str(s.categoria), s.costo, s.moneda, s.get_frecuencia_display(), s.costo_mensual,
              s.costo_anual, s.fecha_inicio, s.proxima_renovacion, s.get_estado_display(), s.responsable, s.descripcion]
             for s in qs)
    filtros = _describir(f, {'q': 'Búsqueda', 'estado': 'Estado', 'proveedor': 'Proveedor', 'renovacion': 'Renovación'},
                         {'renovacion': lambda v: {'30': 'en 30 días', '90': 'en 90 días', 'vencida': 'vencida'}.get(v, v)})
    return respuesta_excel('Suscripciones', columnas, filas, request, filtros)
