"""
Registro de módulos que usan la papelera. Cada módulo se registra una vez (en su apps.ready):

    papelera.registrar(Ticket, etiqueta='Tickets', url_detalle='ticket_detalle')

La pantalla /papelera/ lista lo eliminado de todos los módulos registrados; restaurar lo pueden hacer
Administrador e IT Support, el borrado definitivo solo el Administrador.
"""
REGISTRO = {}


def clave(modelo):
    return f'{modelo._meta.app_label}.{modelo._meta.model_name}'


def registrar(modelo, etiqueta, url_detalle=None):
    REGISTRO[clave(modelo)] = {'modelo': modelo, 'etiqueta': etiqueta, 'url_detalle': url_detalle}


def modulo(clave_modelo):
    return REGISTRO.get(clave_modelo)
