from django.utils.http import url_has_allowed_host_and_scheme


def destino_seguro(valor, por_defecto):
    """Solo acepta rutas internas de la app ('/tareas/?x=1'); cualquier otra cosa (otro dominio, 'javascript:',
    '//sitio') se reemplaza por `por_defecto`. Evita redirecciones abiertas con el parámetro 'volver'."""
    valor = (valor or '').strip()
    if valor.startswith('/') and not valor.startswith('//') and \
            url_has_allowed_host_and_scheme(valor, allowed_hosts=None, require_https=False):
        return valor
    return por_defecto
