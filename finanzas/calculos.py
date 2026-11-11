"""
Cálculos financieros (todo en Decimal, convertido explícitamente a la moneda del reporte).
"""
import calendar
from datetime import date
from decimal import Decimal

from .models import CRC, USD, Gasto, Presupuesto, Suscripcion, TipoCambio, convertir, redondear

CERO = Decimal('0.00')


def sumar_meses(d, n):
    m = d.month - 1 + n
    a, m = d.year + m // 12, m % 12 + 1
    return date(a, m, min(d.day, calendar.monthrange(a, m)[1]))


def renovaciones(sus, desde, hasta):
    """Fechas de cobro de una suscripción activa entre `desde` y `hasta` (inclusive)."""
    if sus.estado != 'activa' or not sus.proxima_renovacion:
        return []
    fechas, f, paso = [], sus.proxima_renovacion, sus.meses_periodo
    while f < desde:
        f = sumar_meses(f, paso)
    while f <= hasta:
        fechas.append(f)
        f = sumar_meses(f, paso)
    return fechas


def meses_transcurridos(anio, hoy):
    if anio < hoy.year:
        return 12
    if anio > hoy.year:
        return 0
    return hoy.month


def resumen_anual(anio, moneda, hoy):
    """Presupuesto vs gasto real del año, por categoría y por mes, con proyección de cierre.

    Gastos 'anulado' no cuentan. 'Utilizado' = pendientes + pagados. Lo que no se puede convertir por falta de
    tipo de cambio queda fuera de los totales y se lista en `sin_tipo` (nunca se suma ni se descarta en silencio).
    """
    otra = CRC if moneda == USD else USD
    presupuestos = list(Presupuesto.objects.filter(anio=anio).select_related('categoria'))
    gastos = list(Gasto.objects.filter(fecha__year=anio).exclude(estado='anulado').select_related('categoria'))
    tipo_anual = TipoCambio.promedio_del_anio(anio)

    filas, sin_tipo, presupuesto_sin_tipo = {}, [], []

    def fila(categoria):
        return filas.setdefault(categoria.pk, {'categoria': categoria, 'asignado': CERO, 'utilizado': CERO,
                                               'pagado': CERO, 'pendiente': CERO, 'suscripciones': CERO})

    for p in presupuestos:
        valor = p.monto_en(moneda)
        if valor is None:
            presupuesto_sin_tipo.append(p)
            fila(p.categoria)
        else:
            fila(p.categoria)['asignado'] += valor

    por_mes = [CERO] * 12
    for g in gastos:
        valor = g.monto_en(moneda)
        if valor is None:
            sin_tipo.append(g)
            continue
        r = fila(g.categoria)
        r['utilizado'] += valor
        r['pagado' if g.estado == 'pagado' else 'pendiente'] += valor
        por_mes[g.fecha.month - 1] += valor

    # Suscripciones activas: cobros que caen en el año (compromiso), convertidos con el tipo de cada mes.
    suscripciones_sin_tipo = []
    for s in Suscripcion.objects.filter(estado='activa').select_related('categoria'):
        for f in renovaciones(s, date(anio, 1, 1), date(anio, 12, 31)):
            tipo = TipoCambio.del_mes(f.year, f.month) or tipo_anual
            valor = convertir(s.costo, s.moneda, moneda, tipo)
            if valor is None:
                suscripciones_sin_tipo.append(s)
            else:
                fila(s.categoria)['suscripciones'] += valor

    transcurridos = meses_transcurridos(anio, hoy)
    total = {'asignado': CERO, 'utilizado': CERO, 'pagado': CERO, 'pendiente': CERO, 'suscripciones': CERO, 'proyeccion': CERO}
    lista = []
    for r in sorted(filas.values(), key=lambda x: x['categoria'].nombre):
        r['disponible'] = r['asignado'] - r['utilizado']
        r['ejecucion'] = (r['utilizado'] / r['asignado'] * 100) if r['asignado'] else None
        r['proyeccion'] = redondear(r['utilizado'] / transcurridos * 12) if transcurridos else CERO
        r['excede'] = r['asignado'] and r['proyeccion'] > r['asignado']
        for k in total:
            total[k] += r[k]
        lista.append(r)
    total['disponible'] = total['asignado'] - total['utilizado']
    total['ejecucion'] = (total['utilizado'] / total['asignado'] * 100) if total['asignado'] else None
    maximo = max(por_mes) if any(por_mes) else Decimal('1')
    return {
        'anio': anio, 'moneda': moneda, 'otra_moneda': otra, 'categorias': lista, 'total': total,
        'por_mes': [{'mes': i + 1, 'monto': m, 'pct': int(m / maximo * 100) if maximo else 0} for i, m in enumerate(por_mes)],
        'meses_transcurridos': transcurridos, 'tipo_anual': tipo_anual,
        'sin_tipo': sin_tipo, 'presupuesto_sin_tipo': presupuesto_sin_tipo,
        'suscripciones_sin_tipo': list(dict.fromkeys(suscripciones_sin_tipo)),
    }
