"""
Tareas y calendario. Consultan los tres roles; crean/editan/eliminan Administrador e IT Support
(eliminar = papelera; borrado definitivo solo Administrador desde la Papelera).
"""
import calendar as cal
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.db.models.functions import ExtractMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import roles
from core.auditoria import auditar

from .forms import TareaForm
from .models import Tarea

EDITAN = (roles.ADMIN, roles.IT)
CAMPOS = ['titulo', 'descripcion', 'estado', 'prioridad', 'fecha_vencimiento', 'responsable']
ORDENES = {
    'vencimiento': ('Vencimiento', None),  # orden por defecto del modelo (sin fecha al final)
    'prioridad': ('Prioridad (urgente primero)', ['orden_prioridad', 'fecha_vencimiento']),
    'recientes': ('Más recientes', ['-creado_en']),
    'estado': ('Pendientes primero', ['orden_estado', 'fecha_vencimiento']),
}


def _legible(t, campo):
    if campo == 'responsable':
        return (t.responsable.get_full_name() or t.responsable.username) if t.responsable else 'Sin responsable'
    if campo in ('estado', 'prioridad'):
        return getattr(t, f'get_{campo}_display')()
    if campo == 'fecha_vencimiento':
        return t.fecha_vencimiento.strftime('%d/%m/%Y') if t.fecha_vencimiento else ''
    if campo == 'descripcion':
        return (t.descripcion[:120] + '…') if len(t.descripcion) > 120 else t.descripcion
    return getattr(t, campo) or ''


@roles.requiere_rol()
def tarea_lista(request):
    hoy = timezone.localdate()
    qs = Tarea.objects.select_related('responsable').annotate(
        orden_prioridad=Case(*[When(prioridad=k, then=Value(v)) for k, v in Tarea.PRIORIDAD_ORDEN.items()],
                             default=Value(9), output_field=IntegerField()),
        orden_estado=Case(When(estado='completada', then=Value(1)), default=Value(0), output_field=IntegerField()))
    g = request.GET
    f = {k: g.get(k, '').strip() for k in ('q', 'estado', 'prioridad', 'responsable', 'vence', 'orden')}
    if f['estado'] == 'abiertas':
        qs = qs.exclude(estado='completada')
    elif f['estado']:
        qs = qs.filter(estado=f['estado'])
    if f['prioridad']:
        qs = qs.filter(prioridad=f['prioridad'])
    if f['responsable'] == 'ninguno':
        qs = qs.filter(responsable__isnull=True)
    elif f['responsable'].isdigit():
        qs = qs.filter(responsable_id=f['responsable'])
    if f['vence'] == 'vencidas':
        qs = qs.filter(fecha_vencimiento__lt=hoy).exclude(estado='completada')
    elif f['vence'] == 'hoy':
        qs = qs.filter(fecha_vencimiento=hoy)
    elif f['vence'] == 'semana':
        qs = qs.filter(fecha_vencimiento__range=(hoy, hoy + timedelta(days=7)))
    elif f['vence'] == 'sin_fecha':
        qs = qs.filter(fecha_vencimiento__isnull=True)
    if f['q']:
        qs = qs.filter(Q(titulo__icontains=f['q']) | Q(descripcion__icontains=f['q']))
    if f['orden'] not in ORDENES:
        f['orden'] = 'vencimiento'
    if ORDENES[f['orden']][1]:
        qs = qs.order_by(*ORDENES[f['orden']][1])
    pagina = Paginator(qs, 25).get_page(g.get('page'))
    sin_pagina = g.copy()
    sin_pagina.pop('page', None)

    abiertas = Tarea.objects.exclude(estado='completada')
    return render(request, 'tareas/lista.html', {
        'pagina': pagina, 'total': pagina.paginator.count, 'query_sin_pagina': sin_pagina.urlencode(),
        'filtros': f, 'hay_filtros': any(f[k] for k in ('q', 'estado', 'prioridad', 'responsable', 'vence')),
        'estados': Tarea.ESTADO_CHOICES, 'prioridades': Tarea.PRIORIDAD_CHOICES,
        'ordenes': [(k, v[0]) for k, v in ORDENES.items()],
        'responsables': User.objects.filter(tareas_asignadas__isnull=False).distinct().order_by('first_name'),
        'proximas': abiertas.filter(fecha_vencimiento__range=(hoy, hoy + timedelta(days=7)))
                            .select_related('responsable').order_by('fecha_vencimiento')[:8],
        'kpi': {
            'total': Tarea.objects.count(),
            'pendientes': Tarea.objects.filter(estado='pendiente').count(),
            'en_progreso': Tarea.objects.filter(estado='en_progreso').count(),
            'completadas': Tarea.objects.filter(estado='completada').count(),
            'vencidas': abiertas.filter(fecha_vencimiento__lt=hoy).count(),
        },
        'hoy': hoy,
    })


@roles.requiere_rol(*EDITAN)
def tarea_crear(request):
    inicial = {}
    fecha = request.GET.get('fecha', '')
    try:
        inicial['fecha_vencimiento'] = date.fromisoformat(fecha)
    except ValueError:
        pass
    form = TareaForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        t = form.save(commit=False)
        t.creado_por = request.user
        t.save()
        auditar(request, 'CREADA', 'tareas', objeto=t, detalle=t.resumen_para_auditoria())
        messages.success(request, f'Tarea "{t.titulo}" creada.')
        return redirect(request.POST.get('volver') or 'tarea_lista')
    return render(request, 'tareas/form.html', {'form': form, 'tarea': None, 'volver': request.GET.get('volver', '')})


@roles.requiere_rol()
def tarea_editar(request, pk):
    """Detalle + edición. Solo lectura ve el formulario deshabilitado (y el servidor rechaza el POST)."""
    t = get_object_or_404(Tarea.todos.select_related('responsable', 'creado_por'), pk=pk)
    editable = roles.puede_editar(request.user) and not t.en_papelera
    form = TareaForm(request.POST or None, instance=t)
    if request.method == 'POST':
        if not editable:
            return roles.denegado(request, 'No puedes modificar esta tarea.')
        antes = {c: _legible(t, c) for c in CAMPOS}
        if form.is_valid():
            t = form.save(commit=False)
            cambios = {c: [antes[c], _legible(t, c)] for c in CAMPOS if antes[c] != _legible(t, c)}
            if not cambios:
                messages.info(request, 'Sin cambios.')
            else:
                t.save()
                auditar(request, 'EDITADA', 'tareas', objeto=t, cambios=cambios)
                messages.success(request, 'Tarea actualizada.')
            return redirect(request.POST.get('volver') or 'tarea_lista')
    if not editable:
        for campo in form.fields.values():
            campo.disabled = True
    return render(request, 'tareas/form.html', {'form': form, 'tarea': t, 'editable': editable,
                                                'volver': request.GET.get('volver', '')})


@require_POST
@roles.requiere_rol(*EDITAN)
def tarea_estado(request, pk):
    """Cambio rápido de estado desde la lista o el calendario."""
    t = get_object_or_404(Tarea, pk=pk)
    nuevo = request.POST.get('estado')
    if nuevo in dict(Tarea.ESTADO_CHOICES) and nuevo != t.estado:
        antes = t.get_estado_display()
        t.estado = nuevo
        t.save()
        auditar(request, 'EDITADA', 'tareas', objeto=t, cambios={'estado': [antes, t.get_estado_display()]})
        messages.success(request, f'"{t.titulo}": {t.get_estado_display()}.')
    return redirect(request.POST.get('volver') or 'tarea_lista')


@require_POST
@roles.requiere_rol(*EDITAN)
def tarea_eliminar(request, pk):
    t = get_object_or_404(Tarea, pk=pk)
    t.enviar_a_papelera(request.user)
    auditar(request, 'ENVIADO_A_PAPELERA', 'tareas', objeto=t)
    messages.success(request, f'Tarea "{t.titulo}" enviada a la papelera.')
    return redirect('tarea_lista')


# ------------------ calendario ------------------

VISTAS = ('mes', 'semana', 'dia', 'anio')


def _fecha(valor, por_defecto):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return por_defecto


def _sumar_meses(d, n):
    m = d.month - 1 + n
    a, m = d.year + m // 12, m % 12 + 1
    return date(a, m, min(d.day, cal.monthrange(a, m)[1]))


def _json_tareas(tareas):
    """Datos para el panel de detalle (una sola fuente; las celdas solo llevan el id)."""
    return {t.pk: {'titulo': t.titulo, 'descripcion': t.descripcion, 'estado': t.get_estado_display(),
                   'color_estado': t.color_estado, 'prioridad': t.get_prioridad_display(),
                   'color_prioridad': t.color_prioridad,
                   'vence': t.fecha_vencimiento.strftime('%d/%m/%Y') if t.fecha_vencimiento else '',
                   'responsable': (t.responsable.get_full_name() or t.responsable.username) if t.responsable else '',
                   'vencida': t.vencida} for t in tareas}


@roles.requiere_rol()
def calendario(request, vista='mes'):
    if vista not in VISTAS:
        vista = 'mes'
    hoy = timezone.localdate()
    fecha = _fecha(request.GET.get('fecha'), hoy)
    base = Tarea.objects.select_related('responsable')
    ctx = {'vista': vista, 'fecha': fecha, 'hoy': hoy, 'vistas': [('anio', 'Año'), ('mes', 'Mes'), ('semana', 'Semana'), ('dia', 'Día')]}

    if vista == 'anio':
        conteo = dict(base.filter(fecha_vencimiento__year=fecha.year)
                      .annotate(m=ExtractMonth('fecha_vencimiento')).values('m').annotate(n=Count('id')).values_list('m', 'n'))
        abiertas = dict(base.filter(fecha_vencimiento__year=fecha.year).exclude(estado='completada')
                        .annotate(m=ExtractMonth('fecha_vencimiento')).values('m').annotate(n=Count('id')).values_list('m', 'n'))
        dias_con = set(base.filter(fecha_vencimiento__year=fecha.year).values_list('fecha_vencimiento', flat=True))
        semanas_cal = cal.Calendar(firstweekday=0)
        ctx['meses'] = [{'fecha': date(fecha.year, m, 1), 'total': conteo.get(m, 0), 'abiertas': abiertas.get(m, 0),
                         'semanas': [[{'d': d, 'en_mes': d.month == m, 'con': d in dias_con} for d in sem]
                                     for sem in semanas_cal.monthdatescalendar(fecha.year, m)]}
                        for m in range(1, 13)]
        ctx['anterior'], ctx['siguiente'] = date(fecha.year - 1, 1, 1), date(fecha.year + 1, 1, 1)
        ctx['titulo'] = str(fecha.year)
        tareas = []
    else:
        if vista == 'mes':
            semanas = cal.Calendar(firstweekday=0).monthdatescalendar(fecha.year, fecha.month)
            inicio, fin = semanas[0][0], semanas[-1][-1]
            ctx['anterior'], ctx['siguiente'] = _sumar_meses(fecha, -1).replace(day=1), _sumar_meses(fecha, 1).replace(day=1)
        elif vista == 'semana':
            inicio = fecha - timedelta(days=fecha.weekday())
            fin = inicio + timedelta(days=6)
            semanas = [[inicio + timedelta(days=i) for i in range(7)]]
            ctx['anterior'], ctx['siguiente'] = fecha - timedelta(days=7), fecha + timedelta(days=7)
        else:  # dia
            inicio = fin = fecha
            semanas = []
            ctx['anterior'], ctx['siguiente'] = fecha - timedelta(days=1), fecha + timedelta(days=1)
        tareas = list(base.filter(fecha_vencimiento__range=(inicio, fin)))
        por_dia = {}
        for t in tareas:
            por_dia.setdefault(t.fecha_vencimiento, []).append(t)
        ctx['semanas'] = [[{'d': d, 'en_mes': vista != 'mes' or d.month == fecha.month, 'tareas': por_dia.get(d, [])}
                           for d in sem] for sem in semanas]
        ctx['del_dia'] = por_dia.get(fecha, [])
        ctx['resumen_dia'] = {e: sum(1 for t in ctx['del_dia'] if t.estado == e) for e, _ in Tarea.ESTADO_CHOICES}

    ctx['tareas_json'] = {str(k): v for k, v in _json_tareas(tareas).items()}
    ctx['sin_fecha'] = Tarea.objects.filter(fecha_vencimiento__isnull=True).exclude(estado='completada').count()
    return render(request, 'tareas/calendario.html', ctx)
