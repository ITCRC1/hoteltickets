"""
Envío de notificaciones por correo electrónico.

Configura los siguientes ajustes en .env:
  EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD
  DEFAULT_FROM_EMAIL
  NOTIFICATION_EMAILS  (lista de correos separados por coma, para alertas a técnicos/admins)
"""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def _construir_url(ticket):
    """Construye la URL pública del detalle del ticket."""
    base = getattr(settings, 'SITE_URL', '').rstrip('/')
    if not base:
        return ''
    return f"{base}{reverse('ticket_detalle', kwargs={'pk': ticket.pk})}"


def _enviar(asunto, plantilla, contexto, destinatarios):
    """Helper interno: renderiza una plantilla .txt y envía el correo."""
    destinatarios = [d for d in destinatarios if d]
    if not destinatarios:
        return
    try:
        cuerpo = render_to_string(f'emails/{plantilla}.txt', contexto)
        msg = EmailMultiAlternatives(
            subject=asunto,
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=destinatarios,
        )
        msg.send(fail_silently=False)
        logger.info('Correo enviado: %s → %s', asunto, destinatarios)
    except Exception as exc:
        logger.error('Error enviando correo "%s": %s', asunto, exc)


def notificar_ticket_creado(ticket):
    """Cuando se crea un ticket nuevo:
    - Alerta a los emails configurados en NOTIFICATION_EMAILS.
    - Envía confirmación al solicitante.
    """
    contexto = {'ticket': ticket, 'url': _construir_url(ticket)}

    # 1) Alerta a técnicos / admins
    admins = getattr(settings, 'NOTIFICATION_EMAILS', [])
    # fincontroller_email = 'fincontroller@seedcostarica.com'
    # isaac_email = 'isaac@thecostaricacollection.com'
    if admins:
        destinatarios = admins
        # Para enviar siempre también a fincontroller@seedcostarica.com e isaac@thecostaricacollection.com,
        # descomenta la siguiente línea:
        # destinatarios = admins + [fincontroller_email, isaac_email]
        _enviar(
            asunto=f'Nuevo ticket · {ticket.get_prioridad_display()} · {ticket.titulo}',
            plantilla='ticket_creado_admin',
            contexto=contexto,
            destinatarios=destinatarios,
        )

    # 2) Confirmación al solicitante
    if ticket.solicitante_email:
        _enviar(
            asunto=f'Recibimos tu reporte · {ticket.hotel.nombre}',
            plantilla='ticket_recibido_solicitante',
            contexto=contexto,
            destinatarios=[ticket.solicitante_email],
        )


def notificar_comentario(comentario):
    """Cuando se añade un comentario público al ticket."""
    if comentario.interno:
        return  # las notas internas no se envían al solicitante
    ticket = comentario.ticket
    if ticket.solicitante_email:
        _enviar(
            asunto=f'[Ticket #{ticket.id}] Nueva actualización',
            plantilla='ticket_comentario',
            contexto={
                'ticket': ticket,
                'comentario': comentario,
                'url': _construir_url(ticket),
            },
            destinatarios=[ticket.solicitante_email],
        )


def notificar_resolucion(ticket):
    """Cuando el ticket se marca como resuelto."""
    if ticket.solicitante_email:
        _enviar(
            asunto=f'[Ticket #{ticket.id}] Resuelto · {ticket.titulo}',
            plantilla='ticket_resuelto',
            contexto={'ticket': ticket, 'url': _construir_url(ticket)},
            destinatarios=[ticket.solicitante_email],
        )
