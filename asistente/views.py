"""
Pantallas del asistente: chat por usuario, confirmación de acciones y configuración (Administrador).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import roles
from core.auditoria import auditar
from core.models import Auditoria, Parametro

from . import herramientas, motor
from .models import AccionPendiente, Conversacion, Mensaje

# Precios de referencia de claude-opus-5-5 (USD por millón de tokens) para estimar el costo en pantalla.
PRECIO_ENTRADA, PRECIO_SALIDA, PRECIO_CACHE = Decimal('4'), Decimal('20'), Decimal('0.20')


@roles.requiere_rol()
def asistente(request, pk=None):
    conversaciones = Conversacion.objects.filter(usuario=request.user)[:30]
    actual = get_object_or_404(Conversacion, pk=pk, usuario=request.user) if pk else None
    return render(request, 'asistente/chat.html', {
        'habilitado': motor.habilitado(), 'clave': motor.clave_configurada(),
        'conversaciones': conversaciones, 'actual': actual,
        'mensajes': actual.mensajes.filter(visible=True) if actual else [],
        'acciones': actual.acciones.all() if actual else [],
        'acciones_habilitadas': motor.acciones_habilitadas(),
    })


@require_POST
@roles.requiere_rol()
def enviar(request, pk=None):
    texto = request.POST.get('texto', '').strip()[:4000]
    if not texto:
        return redirect('asistente_conversacion', pk=pk) if pk else redirect('asistente')
    conversacion = (get_object_or_404(Conversacion, pk=pk, usuario=request.user) if pk
                    else Conversacion.objects.create(usuario=request.user))
    try:
        motor.responder(conversacion, request.user, texto)
    except (motor.AsistenteNoDisponible, motor.ErrorIA) as e:
        messages.error(request, str(e))
    return redirect('asistente_conversacion', pk=conversacion.pk)


@require_POST
@roles.requiere_rol()
def accion_resolver(request, pk, decision):
    if decision not in ('confirmar', 'rechazar'):
        raise Http404
    accion = get_object_or_404(AccionPendiente, pk=pk, usuario=request.user, estado='pendiente')
    if decision == 'confirmar':
        ok, resultado = herramientas.ejecutar_accion(accion, request.user, request)
        accion.estado, accion.resultado = ('confirmada' if ok else 'error'), resultado
        aviso = f'(Aviso del sistema) El usuario CONFIRMÓ la acción #{accion.pk}. Resultado: {resultado}'
        (messages.success if ok else messages.error)(request, resultado if ok else f'No se pudo: {resultado}')
    else:
        accion.estado, accion.resultado = 'rechazada', 'Rechazada por el usuario'
        aviso = f'(Aviso del sistema) El usuario RECHAZÓ la acción #{accion.pk}; no se guardó nada.'
        messages.info(request, 'Acción rechazada: no se guardó nada.')
    accion.resuelta_en = timezone.now()
    accion.save()
    # El modelo se entera en el próximo turno (mensaje de usuario no visible, al final del historial).
    Mensaje.objects.create(conversacion=accion.conversacion, rol='user', contenido=[{'type': 'text', 'text': aviso}],
                           texto=aviso, visible=False)
    return redirect('asistente_conversacion', pk=accion.conversacion_id)


@require_POST
@roles.requiere_rol()
def conversacion_borrar(request, pk):
    c = get_object_or_404(Conversacion, pk=pk, usuario=request.user)
    c.delete()
    messages.success(request, 'Conversación eliminada.')
    return redirect('asistente')


@roles.requiere_rol(roles.ADMIN)
def configuracion_ia(request):
    if request.method == 'POST':
        cambios = {}
        for clave in ('ia_habilitada', 'ia_acciones'):
            nuevo = 'si' if request.POST.get(clave) == 'on' else 'no'
            antes = Parametro.obtener(clave, 'si')
            if antes != nuevo:
                Parametro.objects.update_or_create(clave=clave, defaults={'valor': nuevo, 'actualizado_por': request.user})
                cambios[clave] = [antes, nuevo]
        if cambios:
            auditar(request, 'EDITADO', 'asistente', detalle='Configuración del asistente', cambios=cambios)
            messages.success(request, 'Configuración del asistente guardada.')
        return redirect('configuracion_ia')

    inicio_mes = timezone.localdate().replace(day=1)
    del_mes = Mensaje.objects.filter(rol='assistant', creado_en__date__gte=inicio_mes)
    totales = del_mes.aggregate(e=Sum('tokens_entrada'), s=Sum('tokens_salida'), c=Sum('tokens_cache'), n=Count('id'))
    e, s, c = (Decimal(totales[k] or 0) for k in ('e', 's', 'c'))
    costo = (e * PRECIO_ENTRADA + s * PRECIO_SALIDA + c * PRECIO_CACHE) / Decimal(1_000_000)
    por_usuario = (del_mes.values('conversacion__usuario__first_name', 'conversacion__usuario__last_name',
                                  'conversacion__usuario__username')
                   .annotate(llamadas=Count('id'), entrada=Sum('tokens_entrada'), salida=Sum('tokens_salida'))
                   .order_by('-salida'))
    return render(request, 'asistente/configuracion.html', {
        'clave': motor.clave_configurada(), 'modelo': motor.MODELO, 'esfuerzo': motor.ESFUERZO,
        'ia_habilitada': Parametro.obtener('ia_habilitada', 'si') == 'si',
        'ia_acciones': Parametro.obtener('ia_acciones', 'si') == 'si',
        'totales': totales, 'costo': costo.quantize(Decimal('0.01')), 'por_usuario': por_usuario,
        'errores': Auditoria.objects.filter(accion='ERROR_IA', creado_en__gte=timezone.now() - timedelta(days=30))[:20],
        'herramientas': [(n, d) for n, (_, d, _) in herramientas.HERRAMIENTAS.items()],
        'acciones': herramientas.ACCIONES,
        'pendientes': AccionPendiente.objects.filter(estado='pendiente').count(),
        'resumen_acciones': dict(AccionPendiente.objects.values_list('estado').annotate(n=Count('id'))),
    })
