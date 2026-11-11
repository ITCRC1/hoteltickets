"""
Vistas del sistema de tickets.

Hay dos zonas:
  1) PÚBLICA — solo la creación de tickets (sin login).
  2) PRIVADA — dashboard, lista, detalle, gestión (requiere login).
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import (Avg, Case, Count, DurationField, ExpressionWrapper, F, IntegerField, Q, Value,
                              When)
from django.http import Http404
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import Ticket, Hotel, Categoria, Comentario, RegistroAuditoria
from .forms import TicketPublicoForm, TicketGestionForm, ComentarioForm
from . import notifications
from core import roles
from core.auditoria import auditar


# ------------------ PÚBLICAS ------------------

def ticket_publico(request):
    """Formulario que el staff de hoteles llena sin necesidad de cuenta.

    Por ahora todos los tickets se etiquetan automáticamente como "IT / Sistemas"
    ya que el sistema solo se usa para esa área. Cuando se sume otra área, mostrar
    el campo en el formulario y eliminar esta asignación automática.
    """
    if request.method == 'POST':
        form = TicketPublicoForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            # Asignación automática de categoría (sólo mientras es solo TI)
            categoria_default, _ = Categoria.objects.get_or_create(
                nombre='IT / Sistemas',
                defaults={'color': '#0d6efd', 'descripcion': 'Computadoras, red, internet, software'},
            )
            ticket.categoria = categoria_default
            ticket.save()

            RegistroAuditoria.registrar(
                ticket=ticket,
                accion='crear',
                usuario=None,
                detalle=f'Ticket creado por {ticket.solicitante_nombre} desde formulario público'
            )
            # Envía correos: alerta a técnicos + confirmación al solicitante
            notifications.notificar_ticket_creado(ticket)
            return redirect('ticket_confirmacion', pk=ticket.pk)
    else:
        form = TicketPublicoForm()
    return render(request, 'tickets/ticket_publico.html', {'form': form})


def ticket_confirmacion(request, pk):
    """Pantalla de 'gracias' con el número de ticket."""
    ticket = get_object_or_404(Ticket, pk=pk)
    return render(request, 'tickets/ticket_confirmacion.html', {'ticket': ticket})


# ------------------ PRIVADAS (con login) ------------------

@roles.requiere_rol()
def dashboard(request):
    """
    Dashboard con métricas. Esta es la 'vitrina' del trabajo realizado.
    Muestra números duros: cuántos tickets, tiempos de respuesta, distribución, etc.
    """
    hoy = timezone.now()
    hace_7d = hoy - timedelta(days=7)
    hace_30d = hoy - timedelta(days=30)

    tickets = Ticket.objects.all()

    # KPIs principales
    total = tickets.count()
    abiertos = tickets.filter(estado='abierto').count()
    en_progreso = tickets.filter(estado='en_progreso').count()
    en_espera = tickets.filter(estado='en_espera').count()
    resueltos = tickets.filter(estado='resuelto').count()
    cerrados = tickets.filter(estado='cerrado').count()

    # Últimos 7 / 30 días
    tickets_7d = tickets.filter(creado_en__gte=hace_7d).count()
    resueltos_7d = tickets.filter(resuelto_en__gte=hace_7d).count()
    resueltos_30d = tickets.filter(resuelto_en__gte=hace_30d).count()

    # Tiempo promedio de resolución (últimos 30 días)
    resueltos_qs = tickets.filter(resuelto_en__isnull=False, resuelto_en__gte=hace_30d)
    tiempo_resolucion_promedio = resueltos_qs.annotate(
        duracion=ExpressionWrapper(F('resuelto_en') - F('creado_en'), output_field=DurationField())
    ).aggregate(promedio=Avg('duracion'))['promedio']

    if tiempo_resolucion_promedio is not None:
        total_minutos = int(tiempo_resolucion_promedio.total_seconds() // 60)
        dias, resto = divmod(total_minutos, 60 * 24)
        horas, minutos = divmod(resto, 60)
        if dias:
            tiempo_resolucion_texto = f'{dias}d {horas}h'
        elif horas:
            tiempo_resolucion_texto = f'{horas}h {minutos}m'
        else:
            tiempo_resolucion_texto = f'{minutos}m'
    else:
        tiempo_resolucion_texto = None

    # Distribución por hotel
    por_hotel = (
        tickets.values('hotel__nombre')
        .annotate(total=Count('id'),
                  abiertos=Count('id', filter=Q(estado__in=['abierto', 'en_progreso', 'en_espera'])),
                  cerrados=Count('id', filter=Q(estado__in=['resuelto', 'cerrado'])))
        .order_by('-total')
    )

    # Distribución por categoría
    por_categoria = (
        tickets.values('categoria__nombre', 'categoria__color')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )

    # Tickets recientes
    recientes = tickets.select_related('hotel', 'categoria', 'asignado_a')[:8]

    context = {
        'total': total,
        'abiertos': abiertos,
        'en_progreso': en_progreso,
        'en_espera': en_espera,
        'resueltos': resueltos,
        'cerrados': cerrados,
        'tickets_7d': tickets_7d,
        'resueltos_7d': resueltos_7d,
        'resueltos_30d': resueltos_30d,
        'tiempo_resolucion_promedio': tiempo_resolucion_texto,
        'por_hotel': por_hotel,
        'por_categoria': por_categoria,
        'recientes': recientes,
        'depto': _resumen_departamento(),
    }
    return render(request, 'tickets/dashboard.html', context)


def _resumen_departamento():
    """Indicadores de todos los módulos para el dashboard (datos reales; presupuesto del año en USD)."""
    from finanzas.calculos import resumen_anual
    from finanzas.models import Suscripcion
    from inventario.models import Activo
    from tareas.models import Tarea

    hoy = timezone.localdate()
    tareas = Tarea.objects.all()
    presupuesto = resumen_anual(hoy.year, 'USD', hoy)
    por_vencer = Suscripcion.objects.filter(estado='activa', proxima_renovacion__range=(hoy, hoy + timedelta(days=30)))
    return {
        'hoy': hoy,
        'tareas': {'total': tareas.count(), 'pendientes': tareas.filter(estado='pendiente').count(),
                   'en_progreso': tareas.filter(estado='en_progreso').count(),
                   'completadas': tareas.filter(estado='completada').count(),
                   'vencidas': tareas.exclude(estado='completada').filter(fecha_vencimiento__lt=hoy).count()},
        'tickets': {'abiertos': Ticket.objects.filter(estado='abierto').count(),
                    'pendientes': Ticket.objects.filter(estado__in=('en_progreso', 'en_espera')).count(),
                    'resueltos': Ticket.objects.filter(estado__in=('resuelto', 'cerrado')).count(),
                    'urgentes': Ticket.objects.filter(estado__in=Ticket.ESTADOS_ABIERTOS, prioridad='urgente').count()},
        'equipos': Activo.objects.count(),
        'proximas': tareas.exclude(estado='completada').filter(fecha_vencimiento__range=(hoy, hoy + timedelta(days=7)))
                          .select_related('responsable').order_by('fecha_vencimiento')[:6],
        'presupuesto': presupuesto['total'],
        'presupuesto_avisos': len(presupuesto['sin_tipo']) + len(presupuesto['presupuesto_sin_tipo']),
        'suscripciones_por_vencer': por_vencer.count(),
        'suscripciones_lista': por_vencer.order_by('proxima_renovacion')[:5],
    }


# Órdenes disponibles en la lista: clave → (etiqueta, orden)
ORDENES = {
    'recientes': ('Más recientes', ['-creado_en']),
    'antiguos': ('Más antiguos', ['creado_en']),
    'prioridad': ('Prioridad (urgente primero)', ['orden_prioridad', '-creado_en']),
    'responsable': ('Responsable', ['asignado_a__first_name', 'asignado_a__username', '-creado_en']),
    'pendientes': ('Pendientes primero', ['finalizado', 'orden_prioridad', '-creado_en']),
    'finalizados': ('Finalizados primero', ['-finalizado', '-creado_en']),
}
POR_PAGINA = 25


def _anotar_orden(qs):
    orden_prioridad = Case(*[When(prioridad=k, then=Value(v)) for k, v in Ticket.PRIORIDAD_ORDEN.items()],
                           default=Value(9), output_field=IntegerField())
    finalizado = Case(When(estado__in=Ticket.ESTADOS_ABIERTOS, then=Value(0)), default=Value(1),
                      output_field=IntegerField())
    return qs.annotate(orden_prioridad=orden_prioridad, finalizado=finalizado)


def filtrar(request):
    """Búsqueda, filtros y orden de la lista. Lo reutiliza la exportación a Excel."""
    qs = _anotar_orden(Ticket.objects.select_related('hotel', 'categoria', 'asignado_a'))
    g = request.GET
    f = {k: g.get(k, '').strip() for k in ('q', 'estado', 'prioridad', 'hotel', 'categoria', 'asignado', 'orden')}

    if f['estado'] == 'abiertos':
        qs = qs.filter(estado__in=Ticket.ESTADOS_ABIERTOS)
    elif f['estado']:
        qs = qs.filter(estado=f['estado'])
    if f['prioridad']:
        qs = qs.filter(prioridad=f['prioridad'])
    if f['hotel'].isdigit():
        qs = qs.filter(hotel_id=f['hotel'])
    if f['categoria'].isdigit():
        qs = qs.filter(categoria_id=f['categoria'])
    if f['asignado'] == 'ninguno':
        qs = qs.filter(asignado_a__isnull=True)
    elif f['asignado'].isdigit():
        qs = qs.filter(asignado_a_id=f['asignado'])
    if f['q']:
        busqueda = (Q(titulo__icontains=f['q']) | Q(descripcion__icontains=f['q']) |
                    Q(solicitante_nombre__icontains=f['q']) | Q(solicitante_email__icontains=f['q']) |
                    Q(departamento__icontains=f['q']))
        if f['q'].lstrip('#').isdigit():
            busqueda |= Q(pk=int(f['q'].lstrip('#')))
        qs = qs.filter(busqueda)

    if f['orden'] not in ORDENES:
        f['orden'] = 'recientes'
    return qs.order_by(*ORDENES[f['orden']][1]), f


@roles.requiere_rol()
def ticket_lista(request):
    """Lista con búsqueda, filtros, orden, contador y paginación."""
    qs, f = filtrar(request)
    g = request.GET
    pagina = Paginator(qs, POR_PAGINA).get_page(g.get('page'))

    sin_pagina = g.copy()
    sin_pagina.pop('page', None)
    responsables = User.objects.filter(tickets_asignados__isnull=False).distinct().order_by('first_name', 'username')
    return render(request, 'tickets/ticket_lista.html', {
        'pagina': pagina,
        'total': pagina.paginator.count,
        'query_sin_pagina': sin_pagina.urlencode(),
        'hay_filtros': any(f[k] for k in ('q', 'estado', 'prioridad', 'hotel', 'categoria', 'asignado')),
        'hoteles': Hotel.objects.filter(activo=True),
        'categorias': Categoria.objects.filter(activa=True),
        'estados': Ticket.ESTADO_CHOICES,
        'prioridades': Ticket.PRIORIDAD_CHOICES,
        'responsables': responsables,
        'ordenes': [(k, v[0]) for k, v in ORDENES.items()],
        'filtros': f,
    })


# Campos de gestión que dejan rastro en el historial: campo → acción del historial
CAMPOS_HISTORIAL = {
    'estado': 'cambio_estado',
    'prioridad': 'cambio_prioridad',
    'asignado_a': 'asignar',
    'categoria': 'cambio_categoria',
    'departamento': 'cambio_departamento',
    'notas_resolucion': 'notas_resolucion',
}


def _legible(ticket, campo):
    """Valor de un campo como lo lee una persona (para el historial)."""
    if campo == 'asignado_a':
        u = ticket.asignado_a
        return (u.get_full_name() or u.username) if u else 'Sin asignar'
    if campo == 'categoria':
        return ticket.categoria.nombre if ticket.categoria_id else ''
    if campo in ('estado', 'prioridad'):
        return getattr(ticket, f'get_{campo}_display')()
    if campo == 'notas_resolucion':
        texto = ticket.notas_resolucion or ''
        return (texto[:120] + '…') if len(texto) > 120 else texto
    return getattr(ticket, campo) or ''


@roles.requiere_rol()
def ticket_detalle(request, pk):
    """Detalle, gestión (estado, prioridad, responsable, notas), comentarios y notas al historial."""
    ticket = get_object_or_404(Ticket.todos.select_related('hotel', 'categoria', 'asignado_a'), pk=pk)
    if ticket.en_papelera and not roles.puede_editar(request.user):
        raise Http404

    form_gestion = TicketGestionForm(instance=ticket)
    form_comentario = ComentarioForm()

    if request.method == 'POST':
        # Solo Administrador e IT Support modifican; Solo lectura consulta (validado aquí, no solo en la plantilla).
        if not roles.puede_editar(request.user):
            return roles.denegado(request, 'Tu rol es de solo lectura: no puedes modificar tickets.')
        if ticket.en_papelera:
            messages.error(request, 'Este ticket está en la papelera: restáuralo para modificarlo.')
            return redirect('ticket_detalle', pk=ticket.pk)
        accion = request.POST.get('accion')

        if accion == 'gestion':
            antes = {c: _legible(ticket, c) for c in CAMPOS_HISTORIAL}
            estado_anterior = ticket.estado
            form_gestion = TicketGestionForm(request.POST, instance=ticket)
            if form_gestion.is_valid():
                t = form_gestion.save(commit=False)
                cambiados = [c for c in CAMPOS_HISTORIAL if _legible(t, c) != antes[c]]
                if not cambiados:
                    messages.info(request, 'Sin cambios.')
                    return redirect('ticket_detalle', pk=t.pk)

                ahora = timezone.now()
                if t.estado != estado_anterior:
                    if t.estado == 'resuelto' and not t.resuelto_en:
                        t.resuelto_en = ahora
                    if t.estado == 'cerrado' and not t.cerrado_en:
                        t.cerrado_en = ahora
                    if estado_anterior in ('resuelto', 'cerrado') and t.estado not in ('resuelto', 'cerrado'):
                        t.resuelto_en = None  # reapertura
                        t.cerrado_en = None
                t.save()

                # Una entrada por campo que de verdad cambió, con su valor anterior y nuevo.
                for campo in cambiados:
                    RegistroAuditoria.registrar(ticket=t, accion=CAMPOS_HISTORIAL[campo], usuario=request.user,
                                                anterior=antes[campo], nuevo=_legible(t, campo))
                if 'estado' in cambiados and t.estado == 'resuelto':
                    notifications.notificar_resolucion(t)
                messages.success(request, 'Ticket actualizado.')
                return redirect('ticket_detalle', pk=t.pk)

        elif accion == 'comentar':
            form_comentario = ComentarioForm(request.POST)
            if form_comentario.is_valid():
                c = form_comentario.save(commit=False)
                c.ticket = ticket
                c.autor = request.user
                c.save()

                # Primera respuesta
                if not ticket.primera_respuesta_en:
                    ticket.primera_respuesta_en = timezone.now()
                    ticket.save(update_fields=['primera_respuesta_en'])

                RegistroAuditoria.registrar(
                    ticket=ticket, accion='comentar', usuario=request.user,
                    detalle=('Nota interna: ' if c.interno else '') + c.contenido[:120]
                )
                # Notificar al solicitante si el comentario es público
                notifications.notificar_comentario(c)
                messages.success(request, 'Comentario añadido.')
                return redirect('ticket_detalle', pk=ticket.pk)

        elif accion == 'nota':
            texto = request.POST.get('nota', '').strip()
            if texto:
                RegistroAuditoria.registrar(ticket=ticket, accion='nota', usuario=request.user, detalle=texto[:2000])
                messages.success(request, 'Nota agregada al historial.')
            else:
                messages.error(request, 'La nota está vacía.')
            return redirect('ticket_detalle', pk=ticket.pk)

    return render(request, 'tickets/ticket_detalle.html', {
        'ticket': ticket,
        'form_gestion': form_gestion,
        'form_comentario': form_comentario,
        'comentarios': ticket.comentarios.select_related('autor').all(),
        'auditoria': ticket.auditoria.select_related('usuario').all(),
    })


@require_POST
@roles.requiere_rol(roles.ADMIN, roles.IT)
def ticket_eliminar(request, pk):
    """Envía el ticket a la papelera (recuperable). El borrado definitivo es solo del Administrador, en la papelera."""
    ticket = get_object_or_404(Ticket, pk=pk)
    ticket.enviar_a_papelera(request.user)
    RegistroAuditoria.registrar(ticket=ticket, accion='eliminar', usuario=request.user,
                                detalle=request.POST.get('motivo', '').strip()[:500])
    auditar(request, 'ENVIADO_A_PAPELERA', 'tickets', objeto=ticket)
    messages.success(request, f'Ticket #{ticket.pk} enviado a la papelera. Puedes restaurarlo desde la Papelera.')
    return redirect('ticket_lista')
