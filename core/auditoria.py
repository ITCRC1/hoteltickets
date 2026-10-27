"""Helper único para escribir en la auditoría general."""
from .models import Auditoria


def _ip(request):
    if request is None:
        return None
    reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (reenviada.split(',')[0].strip() or request.META.get('REMOTE_ADDR')) or None


def nombre_de(user):
    if user is None or not getattr(user, 'is_authenticated', False):
        return 'Sistema'
    return user.get_full_name() or user.username


def auditar(request, accion, modulo, objeto=None, cambios=None, detalle='', usuario=None):
    """Registra una acción. `cambios` = {"campo": [antes, después]}; solo se guardan los que cambiaron."""
    usuario = usuario if usuario is not None else getattr(request, 'user', None)
    if usuario is not None and not getattr(usuario, 'is_authenticated', False):
        usuario = None
    cambios = {k: [str(a) if a is not None else '', str(b) if b is not None else '']
               for k, (a, b) in (cambios or {}).items() if a != b}
    return Auditoria.objects.create(
        usuario=usuario,
        usuario_nombre=nombre_de(usuario),
        accion=accion,
        modulo=modulo,
        objeto_id=str(getattr(objeto, 'pk', '') or ''),
        objeto=str(objeto)[:200] if objeto is not None else '',
        cambios=cambios,
        detalle=detalle,
        ip=_ip(request),
    )
