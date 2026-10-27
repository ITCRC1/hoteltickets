"""
Roles de la plataforma (Grupos de Django) y su verificación en el servidor.

  Administrador  → todo: crea, edita, elimina, administra usuarios y configuración.
  IT Support     → atiende: crea y edita tickets/tareas/inventario; no administra ni borra definitivo.
  Solo lectura   → consulta, busca, filtra y exporta; no modifica nada.

Los permisos se validan en cada vista (no basta con ocultar botones). Para un rol nuevo:
agregarlo a ROLES y a los conjuntos de capacidades de abajo.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

ADMIN = 'Administrador'
IT = 'IT Support'
LECTURA = 'Solo lectura'
ROLES = [ADMIN, IT, LECTURA]

PUEDEN_EDITAR = {ADMIN, IT}
PUEDEN_ADMINISTRAR = {ADMIN}


def rol(user):
    """Rol efectivo del usuario (None si no tiene o está inactivo). El superusuario siempre es Administrador."""
    if not getattr(user, 'is_authenticated', False) or not user.is_active:
        return None
    return rol_asignado(user)


def rol_asignado(user):
    """Rol configurado, aunque el usuario esté desactivado (para mostrarlo en la lista de usuarios)."""
    if user.is_superuser:
        return ADMIN
    cache = getattr(user, '_rol_cache', 'sin-calcular')
    if cache == 'sin-calcular':
        nombres = set(user.groups.values_list('name', flat=True))
        cache = next((r for r in ROLES if r in nombres), None)
        user._rol_cache = cache
    return cache


def puede_editar(user):
    return rol(user) in PUEDEN_EDITAR


def es_admin(user):
    return rol(user) in PUEDEN_ADMINISTRAR


def denegado(request, mensaje):
    return render(request, 'core/denegado.html', {'mensaje': mensaje}, status=403)


def requiere_rol(*permitidos):
    """Login obligatorio + uno de los roles indicados (sin argumentos: cualquier rol)."""
    def deco(vista):
        @login_required
        @wraps(vista)
        def envuelta(request, *args, **kwargs):
            r = rol(request.user)
            if r is None:
                return denegado(request, 'Tu usuario no tiene un rol asignado. Pide acceso al administrador.')
            if permitidos and r not in permitidos:
                return denegado(request, 'Tu rol no tiene permiso para esta sección.')
            return vista(request, *args, **kwargs)
        return envuelta
    return deco


def asignar_rol(user, nuevo_rol):
    """Deja al usuario con exactamente un rol. Administrador = superusuario + staff (entra al admin técnico)."""
    from django.contrib.auth.models import Group
    if nuevo_rol not in ROLES:
        raise ValueError(f'Rol inválido: {nuevo_rol}')
    user.groups.remove(*Group.objects.filter(name__in=ROLES))
    user.groups.add(Group.objects.get(name=nuevo_rol))
    user.is_superuser = user.is_staff = (nuevo_rol == ADMIN)
    user.save(update_fields=['is_superuser', 'is_staff'])
    user._rol_cache = 'sin-calcular'
