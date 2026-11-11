from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def dinero(valor, decimales=2):
    """1234567.5 → '1,234,567.50' (formato contable, igual que en los Excel)."""
    if valor is None or valor == '':
        return '—'
    try:
        return f'{Decimal(valor):,.{int(decimales)}f}'
    except (InvalidOperation, ValueError, TypeError):
        return valor


@register.filter
def porcentaje(valor):
    if valor is None:
        return '—'
    return f'{Decimal(valor):,.1f}%'
