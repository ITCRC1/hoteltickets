from . import roles


def plataforma(request):
    """Rol y capacidades del usuario para las plantillas (los permisos reales se validan en las vistas)."""
    user = getattr(request, 'user', None)
    return {
        'rol_usuario': roles.rol(user) if user else None,
        'puede_editar': roles.puede_editar(user) if user else False,
        'es_admin': roles.es_admin(user) if user else False,
    }
