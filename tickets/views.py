"""
Vistas del sistema de tickets.

Hay dos zonas:
  1) PÚBLICA — solo la creación de tickets (sin login).
  2) PRIVADA — dashboard, lista, detalle, gestión (requiere login).
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Q, F, ExpressionWrapper, DurationField
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import Ticket, Hotel, Categoria, Comentario, RegistroAuditoria
from .forms import TicketPublicoForm, TicketGestionForm, ComentarioForm
from . import notifications


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
            # Asignación automática de prioridad (media por defecto)
            ticket.prioridad = 'media'
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

@login_required
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

    # Distribución por prioridad
    por_prioridad = list(
        tickets.values('prioridad').annotate(total=Count('id')).order_by('prioridad')
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
        'tiempo_resolucion_promedio': tiempo_resolucion_promedio,
        'por_hotel': por_hotel,
        'por_categoria': por_categoria,
        'por_prioridad': por_prioridad,
        'recientes': recientes,
    }
    return render(request, 'tickets/dashboard.html', context)


@login_required
def ticket_lista(request):
    """Lista filtrable de todos los tickets."""
    qs = Ticket.objects.select_related('hotel', 'categoria', 'asignado_a').all()

    # Filtros
    estado = request.GET.get('estado')
    hotel = request.GET.get('hotel')
    prioridad = request.GET.get('prioridad')
    categoria = request.GET.get('categoria')
    buscar = request.GET.get('q', '').strip()

    if estado:
        qs = qs.filter(estado=estado)
    if hotel:
        qs = qs.filter(hotel_id=hotel)
    if prioridad:
        qs = qs.filter(prioridad=prioridad)
    if categoria:
        qs = qs.filter(categoria_id=categoria)
    if buscar:
        qs = qs.filter(
            Q(titulo__icontains=buscar) |
            Q(descripcion__icontains=buscar) |
            Q(solicitante_nombre__icontains=buscar)
        )

    context = {
        'tickets': qs[:200],  # límite simple; cambia por paginación si crece
        'hoteles': Hotel.objects.filter(activo=True),
        'categorias': Categoria.objects.filter(activa=True),
        'estados': Ticket.ESTADO_CHOICES,
        'prioridades': Ticket.PRIORIDAD_CHOICES,
        'filtros': {
            'estado': estado or '',
            'hotel': hotel or '',
            'prioridad': prioridad or '',
            'categoria': categoria or '',
            'q': buscar,
        },
    }
    return render(request, 'tickets/ticket_lista.html', context)


@login_required
def ticket_detalle(request, pk):
    """Detalle, edición de gestión y comentarios."""
    ticket = get_object_or_404(
        Ticket.objects.select_related('hotel', 'categoria', 'asignado_a'),
        pk=pk,
    )

    # Estados anteriores para detectar cambios al guardar el form de gestión
    estado_anterior = ticket.estado
    prioridad_anterior = ticket.prioridad
    asignado_anterior = ticket.asignado_a_id

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'gestion':
            form_gestion = TicketGestionForm(request.POST, instance=ticket)
            form_comentario = ComentarioForm()
            if form_gestion.is_valid():
                t = form_gestion.save(commit=False)

                ahora = timezone.now()
                # Marcar fechas cuando cambia el estado
                if t.estado != estado_anterior:
                    if t.estado == 'resuelto' and not t.resuelto_en:
                        t.resuelto_en = ahora
                    if t.estado == 'cerrado' and not t.cerrado_en:
                        t.cerrado_en = ahora
                    if estado_anterior in ('resuelto', 'cerrado') and t.estado not in ('resuelto', 'cerrado'):
                        # Reapertura: limpiar fechas
                        t.resuelto_en = None
                        t.cerrado_en = None

                t.save()

                # Registrar cambios
                if t.estado != estado_anterior:
                    RegistroAuditoria.registrar(
                        ticket=t, accion='cambio_estado', usuario=request.user,
                        detalle=f'De "{dict(Ticket.ESTADO_CHOICES)[estado_anterior]}" a "{t.get_estado_display()}"'
                    )
                    # Notificar al solicitante si pasó a resuelto
                    if t.estado == 'resuelto' and estado_anterior != 'resuelto':
                        notifications.notificar_resolucion(t)
                if t.prioridad != prioridad_anterior:
                    RegistroAuditoria.registrar(
                        ticket=t, accion='cambio_prioridad', usuario=request.user,
                        detalle=f'De "{dict(Ticket.PRIORIDAD_CHOICES)[prioridad_anterior]}" a "{t.get_prioridad_display()}"'
                    )
                if t.asignado_a_id != asignado_anterior:
                    nombre = t.asignado_a.get_full_name() or t.asignado_a.username if t.asignado_a else 'Sin asignar'
                    RegistroAuditoria.registrar(
                        ticket=t, accion='asignar', usuario=request.user,
                        detalle=f'Asignado a: {nombre}'
                    )
                messages.success(request, 'Ticket actualizado.')
                return redirect('ticket_detalle', pk=t.pk)

        elif accion == 'comentar':
            form_gestion = TicketGestionForm(instance=ticket)
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
    else:
        form_gestion = TicketGestionForm(instance=ticket)
        form_comentario = ComentarioForm()

    comentarios = ticket.comentarios.select_related('autor').all()
    auditoria = ticket.auditoria.select_related('usuario').all()

    return render(request, 'tickets/ticket_detalle.html', {
        'ticket': ticket,
        'form_gestion': form_gestion,
        'form_comentario': form_comentario,
        'comentarios': comentarios,
        'auditoria': auditoria,
    })
