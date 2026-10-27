"""
Invitación por link (igual que Owner Dashboard / Hotel Consolidation): al crear un usuario, o con
"Link de invitación", se genera un link de un solo uso que vence en 7 días; la persona lo abre y define
su propia contraseña. En la base queda solo el SHA-256 del token.
"""
import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from .models import Perfil

INVITE_DIAS = 7


def huella(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


def perfil_de(user):
    perfil, _ = Perfil.objects.get_or_create(usuario=user)
    return perfil


def invitar(user):
    """Genera un link nuevo (el anterior deja de servir). Devuelve el token UNA vez."""
    token = secrets.token_urlsafe(32)
    perfil = perfil_de(user)
    perfil.invite_hash = huella(token)
    perfil.invite_exp = timezone.now() + timedelta(days=INVITE_DIAS)
    perfil.save(update_fields=['invite_hash', 'invite_exp', 'actualizado_en'])
    return token


def pendiente(perfil):
    return bool(perfil and perfil.invite_hash and perfil.invite_exp and perfil.invite_exp > timezone.now())


def usuario_por_token(token):
    """Usuario activo dueño de un link vigente, o None."""
    if not token:
        return None
    perfil = Perfil.objects.select_related('usuario').filter(invite_hash=huella(token)).first()
    if perfil is None or not pendiente(perfil) or not perfil.usuario.is_active:
        return None
    return perfil.usuario


def consumir(user):
    perfil = perfil_de(user)
    perfil.invite_hash, perfil.invite_exp = '', None
    perfil.save(update_fields=['invite_hash', 'invite_exp', 'actualizado_en'])


def validar_password(pw, email=''):
    """Política mínima: 10+ caracteres, letras y números, distinta del correo. Devuelve el error o None."""
    if len(pw) < 10:
        return 'La contraseña debe tener al menos 10 caracteres.'
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        return 'La contraseña debe combinar letras y números.'
    if email and pw.lower() == email.lower():
        return 'La contraseña no puede ser igual al correo.'
    return None
