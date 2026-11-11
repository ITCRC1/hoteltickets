"""
Inventario tecnológico. Consultan los tres roles; registran/editan/eliminan Administrador e IT Support
(eliminar = papelera; borrado definitivo solo Administrador).
"""
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import roles
from core.auditoria import auditar
from tickets.models import Hotel

from .forms import ActivoForm
from .models import GARANTIA_AVISO_DIAS, Activo, CategoriaActivo, EstadoActivo

EDITAN = (roles.ADMIN, roles.IT)
CAMPOS = ActivoForm.Meta.fields
ORDENES = {
    'codigo': ('Código', ['codigo']),
    'nombre': ('Nombre', ['nombre']),
    'categoria': ('Categoría', ['categoria__nombre', 'codigo']),
    'ubicacion': ('Ubicación', ['ubicacion__nombre', 'codigo']),
    'adquisicion': ('Adquisición (reciente primero)', [F('fecha_adquisicion').desc(nulls_last=True), 'codigo']),
    'garantia': ('Garantía (vence primero)', [F('garantia_hasta').asc(nulls_last=True), 'codigo']),
}


def filtrar(request):
    """Aplica búsqueda/filtros/orden de la lista. Lo reutiliza la exportación a Excel."""
    hoy = timezone.localdate()
    qs = Activo.objects.select_related('categoria', 'estado', 'ubicacion')
    g = request.GET
    f = {k: g.get(k, '').strip() for k in ('q', 'categoria', 'estado', 'ubicacion', 'departamento', 'garantia', 'orden')}
    if f['categoria'].isdigit():
        qs = qs.filter(categoria_id=f['categoria'])
    if f['estado'].isdigit():
        qs = qs.filter(estado_id=f['estado'])
    if f['ubicacion'].isdigit():
        qs = qs.filter(ubicacion_id=f['ubicacion'])
    if f['departamento']:
        qs = qs.filter(departamento__iexact=f['departamento'])
    if f['garantia'] == 'vencida':
        qs = qs.filter(garantia_hasta__lt=hoy)
    elif f['garantia'] == 'por_vencer':
        qs = qs.filter(garantia_hasta__range=(hoy, hoy + timedelta(days=GARANTIA_AVISO_DIAS)))
    elif f['garantia'] == 'sin':
        qs = qs.filter(garantia_hasta__isnull=True)
    if f['q']:
        qs = qs.filter(Q(codigo__icontains=f['q']) | Q(nombre__icontains=f['q']) | Q(marca__icontains=f['q']) |
                       Q(modelo__icontains=f['q']) | Q(numero_serie__icontains=f['q']) |
                       Q(responsable__icontains=f['q']) | Q(observaciones__icontains=f['q']))
    if f['orden'] not in ORDENES:
        f['orden'] = 'codigo'
    return qs.order_by(*ORDENES[f['orden']][1]), f


@roles.requiere_rol()
def activo_lista(request):
    qs, f = filtrar(request)
    pagina = Paginator(qs, 25).get_page(request.GET.get('page'))
    sin_pagina = request.GET.copy()
    sin_pagina.pop('page', None)
    hoy = timezone.localdate()
    todos = Activo.objects.all()
    return render(request, 'inventario/lista.html', {
        'pagina': pagina, 'total': pagina.paginator.count, 'query_sin_pagina': sin_pagina.urlencode(),
        'query_filtros': sin_pagina.urlencode(),
        'filtros': f, 'hay_filtros': any(f[k] for k in ('q', 'categoria', 'estado', 'ubicacion', 'departamento', 'garantia')),
        'categorias': CategoriaActivo.objects.all(), 'estados': EstadoActivo.objects.all(),
        'ubicaciones': Hotel.objects.all(),
        'departamentos': todos.exclude(departamento='').order_by('departamento').values_list('departamento', flat=True).distinct(),
        'ordenes': [(k, v[0]) for k, v in ORDENES.items()],
        'stats': {
            'total': todos.count(),
            'por_categoria': todos.values('categoria__nombre').annotate(n=Count('id')).order_by('-n', 'categoria__nombre'),
            'por_estado': todos.values('estado__nombre', 'estado__color').annotate(n=Count('id')).order_by('estado__orden'),
            'por_ubicacion': todos.values('ubicacion__nombre').annotate(n=Count('id')).order_by('-n', 'ubicacion__nombre'),
            'garantia_vencida': todos.filter(garantia_hasta__lt=hoy).count(),
            'garantia_por_vencer': todos.filter(garantia_hasta__range=(hoy, hoy + timedelta(days=GARANTIA_AVISO_DIAS))).count(),
        },
        'aviso_dias': GARANTIA_AVISO_DIAS,
    })


def _legible(a, campo):
    valor = getattr(a, campo)
    if hasattr(valor, 'strftime'):
        return valor.strftime('%d/%m/%Y')
    if campo == 'observaciones' and valor and len(valor) > 120:
        return valor[:120] + '…'
    return str(valor) if valor not in (None, '') else ''


@roles.requiere_rol(*EDITAN)
def activo_crear(request):
    form = ActivoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        a = form.save(commit=False)
        a.creado_por = request.user
        a.save()
        auditar(request, 'CREADO', 'inventario', objeto=a, detalle=a.resumen_para_auditoria())
        messages.success(request, f'Activo {a.codigo} registrado.')
        return redirect('activo_lista')
    return render(request, 'inventario/form.html', {'form': form, 'activo': None})


@roles.requiere_rol()
def activo_editar(request, pk):
    a = get_object_or_404(Activo.todos.select_related('categoria', 'estado', 'ubicacion', 'creado_por'), pk=pk)
    editable = roles.puede_editar(request.user) and not a.en_papelera
    form = ActivoForm(request.POST or None, instance=a)
    if request.method == 'POST':
        if not editable:
            return roles.denegado(request, 'No puedes modificar este activo.')
        antes = {c: _legible(a, c) for c in CAMPOS}
        if form.is_valid():
            a = form.save(commit=False)
            cambios = {c: [antes[c], _legible(a, c)] for c in CAMPOS if antes[c] != _legible(a, c)}
            if cambios:
                a.save()
                auditar(request, 'EDITADO', 'inventario', objeto=a, cambios=cambios)
                messages.success(request, f'Activo {a.codigo} actualizado.')
            else:
                messages.info(request, 'Sin cambios.')
            return redirect('activo_editar', pk=a.pk)
    if not editable:
        for campo in form.fields.values():
            campo.disabled = True
    return render(request, 'inventario/form.html', {'form': form, 'activo': a, 'editable': editable})


@require_POST
@roles.requiere_rol(*EDITAN)
def activo_eliminar(request, pk):
    a = get_object_or_404(Activo, pk=pk)
    a.enviar_a_papelera(request.user)
    auditar(request, 'ENVIADO_A_PAPELERA', 'inventario', objeto=a)
    messages.success(request, f'Activo {a.codigo} enviado a la papelera.')
    return redirect('activo_lista')
