"""
Presupuestos, gastos, tipo de cambio mensual y suscripciones.
Consultan los tres roles; solo el Administrador registra, edita y elimina (eliminar = papelera).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import roles
from core.auditoria import auditar
from core.seguridad import destino_seguro

from .calculos import CERO, renovaciones, resumen_anual, sumar_meses
from .forms import GastoForm, PresupuestoForm, SuscripcionForm, TipoCambioForm
from .models import CRC, MONEDAS, SIMBOLO, USD, CategoriaGasto, Gasto, Presupuesto, Suscripcion, TipoCambio, convertir

ADMIN = roles.ADMIN
MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def _anio(request, por_defecto):
    valor = request.GET.get('anio', '')
    return int(valor) if valor.isdigit() and 2000 <= int(valor) <= 2100 else por_defecto


def _moneda(request):
    return CRC if request.GET.get('moneda') == CRC else USD


def _legible(obj, campo):
    v = getattr(obj, campo)
    if hasattr(v, 'strftime'):
        return v.strftime('%d/%m/%Y')
    return '' if v in (None, '') else str(v)


def _guardar(request, form, obj_antes, modulo, campos, crear_msg, editar_msg):
    """Guarda un formulario de finanzas dejando auditoría (creación con resumen; edición con antes → después)."""
    nuevo = obj_antes is None
    antes = {} if nuevo else {c: _legible(obj_antes, c) for c in campos}
    obj = form.save(commit=False)
    if nuevo:
        obj.creado_por = request.user
        obj.save()
        auditar(request, 'CREADO', modulo, objeto=obj, detalle=obj.resumen_para_auditoria())
        messages.success(request, crear_msg)
        return obj
    cambios = {c: [antes[c], _legible(obj, c)] for c in campos if antes[c] != _legible(obj, c)}
    if cambios:
        obj.save()
        auditar(request, 'EDITADO', modulo, objeto=obj, cambios=cambios)
        messages.success(request, editar_msg)
    else:
        messages.info(request, 'Sin cambios.')
    return obj


def _formulario(request, Modelo, Form, pk, modulo, titulo, volver):
    """Alta/edición genérica. Solo el Administrador guarda; los demás ven el formulario deshabilitado."""
    obj = get_object_or_404(Modelo.todos, pk=pk) if pk else None
    if obj is None and not roles.es_admin(request.user):
        return roles.denegado(request, 'Solo el Administrador registra información financiera.')
    editable = roles.es_admin(request.user) and not (obj and obj.en_papelera)
    inicial = {}
    if obj is None:
        for clave in ('anio', 'categoria', 'fecha', 'moneda'):
            if request.GET.get(clave):
                inicial[clave] = request.GET[clave]
    form = Form(request.POST or None, instance=obj, initial=inicial)
    if request.method == 'POST':
        if not editable:
            return roles.denegado(request, 'Solo el Administrador modifica información financiera.')
        if form.is_valid():
            antes = Modelo.todos.get(pk=obj.pk) if obj else None
            _guardar(request, form, antes, modulo, Form.Meta.fields, f'{titulo} registrado.', f'{titulo} actualizado.')
            return redirect(destino_seguro(request.POST.get('volver'), volver))
    if not editable:
        for campo in form.fields.values():
            campo.disabled = True
    return render(request, 'finanzas/form.html', {
        'form': form, 'obj': obj, 'titulo': titulo, 'editable': editable or obj is None,
        'volver': destino_seguro(request.GET.get('volver'), volver), 'eliminar_url': f'{modulo}_eliminar' if obj else None,
    })


def _eliminar(request, Modelo, pk, modulo, volver):
    obj = get_object_or_404(Modelo, pk=pk)
    obj.enviar_a_papelera(request.user)
    auditar(request, 'ENVIADO_A_PAPELERA', modulo, objeto=obj)
    messages.success(request, f'"{obj}" enviado a la papelera.')
    return redirect(volver)


# ------------------ presupuestos ------------------

@roles.requiere_rol()
def presupuesto_resumen(request):
    hoy = timezone.localdate()
    anio, moneda = _anio(request, hoy.year), _moneda(request)
    resumen = resumen_anual(anio, moneda, hoy)
    return render(request, 'finanzas/presupuestos.html', {
        'r': resumen, 'simbolo': SIMBOLO[moneda], 'meses': MESES,
        'presupuestos': Presupuesto.objects.filter(anio=anio).select_related('categoria'),
        'anios': sorted(set(Presupuesto.objects.values_list('anio', flat=True)) | {hoy.year, anio}, reverse=True),
        'faltan_tipos': [MESES[m - 1] for m in range(1, (resumen['meses_transcurridos'] or 0) + 1)
                         if not TipoCambio.del_mes(anio, m)],
    })


@roles.requiere_rol()
def presupuesto_form(request, pk=None):
    return _formulario(request, Presupuesto, PresupuestoForm, pk, 'presupuesto', 'Presupuesto', 'presupuesto_resumen')


@require_POST
@roles.requiere_rol(ADMIN)
def presupuesto_eliminar(request, pk):
    return _eliminar(request, Presupuesto, pk, 'presupuesto', 'presupuesto_resumen')


# ------------------ gastos ------------------

def filtrar_gastos(request):
    qs = Gasto.objects.select_related('categoria', 'presupuesto')
    g = request.GET
    f = {k: g.get(k, '').strip() for k in ('q', 'anio', 'mes', 'categoria', 'estado', 'moneda')}
    if f['anio'].isdigit():
        qs = qs.filter(fecha__year=int(f['anio']))
    if f['mes'].isdigit():
        qs = qs.filter(fecha__month=int(f['mes']))
    if f['categoria'].isdigit():
        qs = qs.filter(categoria_id=f['categoria'])
    if f['estado']:
        qs = qs.filter(estado=f['estado'])
    if f['moneda'] in (USD, CRC):
        qs = qs.filter(moneda=f['moneda'])
    if f['q']:
        qs = qs.filter(Q(concepto__icontains=f['q']) | Q(proveedor__icontains=f['q']) | Q(observaciones__icontains=f['q']))
    return qs, f


@roles.requiere_rol()
def gasto_lista(request):
    qs, f = filtrar_gastos(request)
    moneda = CRC if request.GET.get('ver') == CRC else USD  # moneda en que se MUESTRA el total ('moneda' filtra)
    total_convertido, sin_tipo, por_moneda = CERO, 0, {USD: CERO, CRC: CERO}
    for gasto in qs.exclude(estado='anulado'):
        por_moneda[gasto.moneda] += gasto.monto
        valor = gasto.monto_en(moneda)
        if valor is None:
            sin_tipo += 1
        else:
            total_convertido += valor
    pagina = Paginator(qs, 25).get_page(request.GET.get('page'))
    sin_pagina = request.GET.copy()
    sin_pagina.pop('page', None)
    otra_vista = sin_pagina.copy()
    otra_vista['ver'] = USD if moneda == CRC else CRC
    return render(request, 'finanzas/gastos.html', {
        'url_otra_moneda': otra_vista.urlencode(), 'otra_moneda': otra_vista['ver'],
        'pagina': pagina, 'total': pagina.paginator.count, 'query_sin_pagina': sin_pagina.urlencode(), 'filtros': f,
        'hay_filtros': any(f[k] for k in f), 'categorias': CategoriaGasto.objects.all(), 'estados': Gasto.ESTADO_CHOICES,
        'monedas': MONEDAS, 'meses': list(enumerate(MESES, start=1)), 'moneda': moneda, 'simbolo': SIMBOLO[moneda],
        'total_convertido': total_convertido, 'sin_tipo': sin_tipo, 'por_moneda': por_moneda,
        'anios': sorted({d.year for d in Gasto.objects.dates('fecha', 'year')} | {timezone.localdate().year}, reverse=True),
    })


@roles.requiere_rol()
def gasto_form(request, pk=None):
    return _formulario(request, Gasto, GastoForm, pk, 'gasto', 'Gasto', 'gasto_lista')


@require_POST
@roles.requiere_rol(ADMIN)
def gasto_eliminar(request, pk):
    return _eliminar(request, Gasto, pk, 'gasto', 'gasto_lista')


# ------------------ tipo de cambio mensual ------------------

@roles.requiere_rol()
def tipos_cambio(request):
    hoy = timezone.localdate()
    anio = _anio(request, hoy.year)
    form = TipoCambioForm(request.POST or None, initial={'anio': anio, 'mes': hoy.month if anio == hoy.year else 1})
    if request.method == 'POST':
        if not roles.es_admin(request.user):
            return roles.denegado(request, 'Solo el Administrador registra tipos de cambio.')
        anio_post, mes_post = request.POST.get('anio', ''), request.POST.get('mes', '')
        existente = (TipoCambio.objects.filter(anio=anio_post, mes=mes_post).first()
                     if anio_post.isdigit() and mes_post.isdigit() else None)
        antes = str(existente.crc_por_usd) if existente else ''  # antes de validar: el form modifica la instancia
        form = TipoCambioForm(request.POST, instance=existente)
        if form.is_valid():
            tc = form.save(commit=False)
            tc.registrado_por = request.user
            tc.save()
            tc.refresh_from_db()  # el valor tal como quedó guardado (4 decimales) para la auditoría
            auditar(request, 'EDITADO' if existente else 'CREADO', 'tipo_cambio', objeto=tc,
                    cambios={'crc_por_usd': [antes, str(tc.crc_por_usd)]})
            messages.success(request, f'Tipo de cambio {tc.mes:02d}/{tc.anio} guardado: ₡{tc.crc_por_usd}.')
            return redirect(f"{request.path}?anio={tc.anio}")
    registrados = {t.mes: t for t in TipoCambio.objects.filter(anio=anio).select_related('registrado_por')}
    return render(request, 'finanzas/tipos_cambio.html', {
        'form': form, 'anio': anio, 'promedio': TipoCambio.promedio_del_anio(anio),
        'filas': [{'mes': m, 'nombre': MESES[m - 1], 'tc': registrados.get(m),
                   'falta': registrados.get(m) is None and date(anio, m, 1) <= hoy} for m in range(1, 13)],
        'anios': sorted(set(TipoCambio.objects.values_list('anio', flat=True)) | {hoy.year, anio}, reverse=True),
    })


# ------------------ suscripciones ------------------

def filtrar_suscripciones(request):
    hoy = timezone.localdate()
    qs = Suscripcion.objects.select_related('categoria')
    g = request.GET
    f = {k: g.get(k, '').strip() for k in ('q', 'estado', 'proveedor', 'renovacion', 'categoria')}
    if f['estado']:
        qs = qs.filter(estado=f['estado'])
    if f['proveedor']:
        qs = qs.filter(proveedor__iexact=f['proveedor'])
    if f['categoria'].isdigit():
        qs = qs.filter(categoria_id=f['categoria'])
    if f['renovacion'] == '30':
        qs = qs.filter(estado='activa', proxima_renovacion__range=(hoy, hoy + timedelta(days=30)))
    elif f['renovacion'] == '90':
        qs = qs.filter(estado='activa', proxima_renovacion__range=(hoy, hoy + timedelta(days=90)))
    elif f['renovacion'] == 'vencida':
        qs = qs.filter(estado='activa', proxima_renovacion__lt=hoy)
    if f['q']:
        qs = qs.filter(Q(nombre__icontains=f['q']) | Q(proveedor__icontains=f['q']) | Q(descripcion__icontains=f['q']))
    return qs, f


@roles.requiere_rol()
def suscripcion_lista(request):
    hoy = timezone.localdate()
    moneda = _moneda(request)
    qs, f = filtrar_suscripciones(request)
    activas = list(Suscripcion.objects.filter(estado='activa'))
    tipo_actual = TipoCambio.del_mes(hoy.year, hoy.month) or TipoCambio.promedio_del_anio(hoy.year)

    mensual, anual, sin_tipo = CERO, CERO, []
    for s in activas:
        m, a = convertir(s.costo_mensual, s.moneda, moneda, tipo_actual), convertir(s.costo_anual, s.moneda, moneda, tipo_actual)
        if m is None:
            sin_tipo.append(s)
        else:
            mensual, anual = mensual + m, anual + a

    # Proyección: cobros de los próximos 12 meses, mes por mes.
    inicio = hoy.replace(day=1)
    proyeccion = []
    for i in range(12):
        desde = sumar_meses(inicio, i)
        hasta = sumar_meses(desde, 1) - timedelta(days=1)
        total = CERO
        for s in activas:
            for fecha in renovaciones(s, desde, hasta):
                valor = convertir(s.costo, s.moneda, moneda, TipoCambio.del_mes(fecha.year, fecha.month) or tipo_actual)
                total += valor or CERO
        proyeccion.append({'mes': desde, 'monto': total})
    maximo = max((p['monto'] for p in proyeccion), default=CERO) or Decimal('1')
    for p in proyeccion:
        p['pct'] = int(p['monto'] / maximo * 100)

    return render(request, 'finanzas/suscripciones.html', {
        'lista': qs, 'filtros': f, 'hay_filtros': any(f.values()), 'moneda': moneda, 'simbolo': SIMBOLO[moneda],
        'kpi': {'activas': len(activas), 'mensual': mensual, 'anual': anual,
                'proximas_30': Suscripcion.objects.filter(estado='activa', proxima_renovacion__range=(hoy, hoy + timedelta(days=30))).count(),
                'vencidas': Suscripcion.objects.filter(estado='activa', proxima_renovacion__lt=hoy).count()},
        'proyeccion': proyeccion, 'total_proyeccion': sum((p['monto'] for p in proyeccion), CERO),
        'sin_tipo': sin_tipo, 'tipo_actual': tipo_actual, 'hoy': hoy,
        'estados': Suscripcion.ESTADO_CHOICES, 'categorias': CategoriaGasto.objects.all(),
        'proveedores': Suscripcion.objects.exclude(proveedor='').order_by('proveedor').values_list('proveedor', flat=True).distinct(),
    })


@roles.requiere_rol()
def suscripcion_form(request, pk=None):
    return _formulario(request, Suscripcion, SuscripcionForm, pk, 'suscripcion', 'Suscripción', 'suscripcion_lista')


@require_POST
@roles.requiere_rol(ADMIN)
def suscripcion_eliminar(request, pk):
    return _eliminar(request, Suscripcion, pk, 'suscripcion', 'suscripcion_lista')


@require_POST
@roles.requiere_rol(ADMIN)
def suscripcion_pagar(request, pk):
    """Registra el cobro de la renovación como gasto pagado y adelanta la próxima renovación un período."""
    s = get_object_or_404(Suscripcion, pk=pk, estado='activa')
    fecha = s.proxima_renovacion or timezone.localdate()
    gasto = Gasto.objects.create(fecha=fecha, concepto=f'Suscripción {s.nombre} ({s.get_frecuencia_display().lower()})',
                                 categoria=s.categoria, proveedor=s.proveedor, monto=s.costo, moneda=s.moneda,
                                 estado='pagado', suscripcion=s, creado_por=request.user)
    antes = s.proxima_renovacion
    s.proxima_renovacion = sumar_meses(fecha, s.meses_periodo)
    s.save(update_fields=['proxima_renovacion', 'actualizado_en'])
    auditar(request, 'PAGO_REGISTRADO', 'suscripcion', objeto=s, detalle=gasto.resumen_para_auditoria(),
            cambios={'proxima_renovacion': [antes.strftime('%d/%m/%Y') if antes else '', s.proxima_renovacion.strftime('%d/%m/%Y')]})
    messages.success(request, f'Pago de {s.nombre} registrado como gasto. Próxima renovación: {s.proxima_renovacion:%d/%m/%Y}.')
    return redirect('suscripcion_lista')
