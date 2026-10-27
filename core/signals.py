"""Auditoría de accesos: ingresos, salidas e intentos fallidos."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .auditoria import auditar


@receiver(user_logged_in)
def _ingreso(sender, request, user, **kwargs):
    auditar(request, 'INGRESO', 'acceso', objeto=user, usuario=user)


@receiver(user_logged_out)
def _salida(sender, request, user, **kwargs):
    if user is not None:
        auditar(request, 'SALIDA', 'acceso', objeto=user, usuario=user)


@receiver(user_login_failed)
def _fallido(sender, credentials, request=None, **kwargs):
    intento = (credentials or {}).get('username', '')
    auditar(request, 'INGRESO_FALLIDO', 'acceso', detalle=f'Usuario/correo: {intento}'[:200])
