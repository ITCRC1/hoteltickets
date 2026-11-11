"""
Configuración general (solo Administrador): catálogos editables, directorio, parámetros y vista del sistema.

Los catálogos se registran en CATALOGOS; cada uno tiene su lista + alta + edición con auditoría.
Los catálogos referenciados por otros registros no se borran: se desactivan (campo activo/activa).
El Directorio sí se puede borrar (no lo referencia ningún registro).
"""
import os

from django import forms
from django.conf import settings
from django.contrib import messages
from django.forms import modelform_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import invitaciones, roles
from .auditoria import auditar
from .models import Directorio, Parametro, destinatarios_avisos


def _catalogos():
    from finanzas.models import CategoriaGasto
    from inventario.models import CategoriaActivo, EstadoActivo
    from tickets.models import Categoria, Hotel
    return {
        'ubicaciones': {'modelo': Hotel, 'titulo': 'Ubicaciones', 'icono': 'geo-alt',
                        'texto': 'Hoteles y puntos externos. Las usan el formulario público, los tickets y el inventario.',
                        'campos': ['nombre', 'tipo', 'ubicacion', 'oficina', 'contacto_principal', 'telefono', 'activo'],
                        'columnas': ['nombre', 'tipo', 'oficina', 'contacto_principal', 'activo']},
        'categorias-tickets': {'modelo': Categoria, 'titulo': 'Categorías de tickets', 'icono': 'tags',
                               'texto': 'Clasificación interna de los tickets.',
                               'campos': ['nombre', 'descripcion', 'color', 'activa'],
                               'columnas': ['nombre', 'descripcion', 'color', 'activa']},
        'categorias-activos': {'modelo': CategoriaActivo, 'titulo': 'Categorías de inventario', 'icono': 'pc-display',
                               'texto': 'Tipos de equipo del inventario.',
                               'campos': ['nombre', 'activa'], 'columnas': ['nombre', 'activa']},
        'estados-activos': {'modelo': EstadoActivo, 'titulo': 'Estados de inventario', 'icono': 'toggles',
                            'texto': 'Estados posibles de un equipo y su color.',
                            'campos': ['nombre', 'color', 'orden', 'activo'], 'columnas': ['nombre', 'color', 'orden', 'activo']},
        'categorias-gasto': {'modelo': CategoriaGasto, 'titulo': 'Categorías de presupuesto y gasto', 'icono': 'wallet2',
                             'texto': 'Categorías de presupuestos, gastos y suscripciones.',
                             'campos': ['nombre', 'activa'], 'columnas': ['nombre', 'activa']},
        'directorio': {'modelo': Directorio, 'titulo': 'Directorio (correo → departamento)', 'icono': 'person-lines-fill',
                       'texto': 'Al reportar, el ticket toma el departamento según el correo de quien reporta.',
                       'campos': ['email', 'nombre', 'departamento'], 'columnas': ['email', 'nombre', 'departamento'],
                       'borrable': True},
    }


def _form(info):
    Form = modelform_factory(info['modelo'], fields=info['campos'])

    class Estilizado(Form):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for nombre, campo in self.fields.items():
                w = campo.widget
                if isinstance(w, forms.CheckboxInput):
                    w.attrs.setdefault('class', 'form-check-input')
                elif nombre == 'color' and isinstance(w, forms.TextInput):  # color hex de categorías de tickets
                    w.input_type = 'color'
                    w.attrs.setdefault('class', 'form-control form-control-color')
                else:
                    w.attrs.setdefault('class', 'form-select' if isinstance(w, forms.Select) else 'form-control')
    return Estilizado


def _valor(obj, campo):
    v = getattr(obj, campo)
    display = getattr(obj, f'get_{campo}_display', None)
    if display:
        return display()
    if isinstance(v, bool):
        return 'sí' if v else 'no'
    return '' if v is None else str(v)


class ParametrosForm(forms.Form):
    destinatarios_avisos = forms.CharField(
        label='Destinatarios de avisos', required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                     'placeholder': 'it@thecostaricacollection.com, otro@thecostaricacollection.com'}),
        help_text='Reciben el aviso de cada ticket nuevo y de cada comentario. Separados por coma.')

    def clean_destinatarios_avisos(self):
        from django.core.validators import validate_email
        correos = [c.strip() for c in self.cleaned_data['destinatarios_avisos'].replace(';', ',').split(',') if c.strip()]
        malos = []
        for c in correos:
            try:
                validate_email(c)
            except forms.ValidationError:
                malos.append(c)
        if malos:
            raise forms.ValidationError(f'Correos no válidos: {", ".join(malos)}')
        return ', '.join(dict.fromkeys(c.lower() for c in correos))


MATRIZ_PERMISOS = [
    ('Ver dashboard, tickets, tareas, calendario, inventario, finanzas y reportes', True, True, True),
    ('Exportar a Excel', True, True, True),
    ('Atender tickets (estado, prioridad, responsable, comentarios, notas)', True, True, False),
    ('Crear y editar tareas y equipos de inventario', True, True, False),
    ('Enviar a la papelera y restaurar (tickets, tareas, inventario)', True, True, False),
    ('Presupuestos, gastos, suscripciones y tipo de cambio', True, False, False),
    ('Borrado definitivo desde la papelera', True, False, False),
    ('Usuarios, roles, auditoría y configuración', True, False, False),
]


@roles.requiere_rol(roles.ADMIN)
def configuracion(request):
    actual = Parametro.objects.filter(clave='destinatarios_avisos').first()
    form = ParametrosForm(request.POST or None, initial={'destinatarios_avisos': ', '.join(destinatarios_avisos())})
    if request.method == 'POST' and form.is_valid():
        nuevo = form.cleaned_data['destinatarios_avisos']
        antes = actual.valor if actual else ', '.join(getattr(settings, 'NOTIFICATION_EMAILS', []))
        Parametro.objects.update_or_create(clave='destinatarios_avisos',
                                           defaults={'valor': nuevo, 'actualizado_por': request.user})
        auditar(request, 'EDITADO', 'configuracion', detalle='Destinatarios de avisos',
                cambios={'destinatarios_avisos': [antes, nuevo]})
        messages.success(request, 'Destinatarios de avisos guardados.' + ('' if nuevo else ' La lista quedó vacía: '
                                                                         'nadie recibirá avisos de tickets nuevos.'))
        return redirect('configuracion')
    from django.contrib.auth.models import User
    cats = _catalogos()
    return render(request, 'core/configuracion.html', {
        'form': form, 'desde_railway': actual is None,
        'catalogos': [(k, v, v['modelo'].objects.count()) for k, v in cats.items()],
        'matriz': MATRIZ_PERMISOS,
        'sistema': {
            'version': (os.environ.get('RAILWAY_GIT_COMMIT_SHA') or '')[:7] or 'local',
            'ambiente': os.environ.get('RAILWAY_ENVIRONMENT_NAME') or 'local',
            'usuarios_activos': User.objects.filter(is_active=True).count(),
            'sesion_minutos': settings.SESSION_COOKIE_AGE // 60,
            'invitacion_dias': invitaciones.INVITE_DIAS,
            'correo_activo': bool(getattr(settings, 'BREVO_API_KEY', '')) or 'smtp' in settings.EMAIL_BACKEND.lower()
                             or 'anymail' in settings.EMAIL_BACKEND.lower(),
            'ia_configurada': bool(os.environ.get('ANTHROPIC_API_KEY')),
        },
    })


@roles.requiere_rol(roles.ADMIN)
def catalogo(request, nombre, pk=None):
    info = _catalogos().get(nombre)
    if info is None:
        raise Http404
    Modelo, Form = info['modelo'], _form(info)
    obj = get_object_or_404(Modelo, pk=pk) if pk else None
    antes = {c: _valor(obj, c) for c in info['campos']} if obj else None
    form = Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        nuevo = form.save()
        if obj is None:
            auditar(request, 'CREADO', 'configuracion', objeto=nuevo, detalle=info['titulo'])
            messages.success(request, f'"{nuevo}" agregado.')
        else:
            cambios = {c: [antes[c], _valor(nuevo, c)] for c in info['campos'] if antes[c] != _valor(nuevo, c)}
            if cambios:
                auditar(request, 'EDITADO', 'configuracion', objeto=nuevo, cambios=cambios, detalle=info['titulo'])
                messages.success(request, f'"{nuevo}" actualizado.')
            else:
                messages.info(request, 'Sin cambios.')
        return redirect('catalogo', nombre=nombre)
    filas = [{'obj': o, 'valores': [_valor(o, c) for c in info['columnas']]} for o in Modelo.objects.all()]
    return render(request, 'core/catalogo.html', {
        'info': info, 'nombre': nombre, 'form': form, 'obj': obj, 'filas': filas,
        'encabezados': [Modelo._meta.get_field(c).verbose_name for c in info['columnas']],
    })


@require_POST
@roles.requiere_rol(roles.ADMIN)
def catalogo_borrar(request, nombre, pk):
    info = _catalogos().get(nombre)
    if info is None or not info.get('borrable'):
        raise Http404
    obj = get_object_or_404(info['modelo'], pk=pk)
    auditar(request, 'ELIMINADO', 'configuracion', objeto=obj, detalle=f'{info["titulo"]}: {obj}')
    obj.delete()
    messages.success(request, f'"{obj}" eliminado del directorio.')
    return redirect('catalogo', nombre=nombre)
