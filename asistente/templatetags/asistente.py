"""Markdown mínimo y seguro para las respuestas del asistente.

Primero se escapa TODO el HTML; después se convierten solo: **negrita**, `código`, enlaces [texto](/ruta) a rutas
internas de la app (nunca a otros dominios ni javascript:), listas con '-', '*' o '1.', títulos '#' y saltos de línea.
"""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

ENLACE = re.compile(r'\[([^\]]+)\]\((/[^)\s]*)\)')
NEGRITA = re.compile(r'\*\*(.+?)\*\*')
CODIGO = re.compile(r'`([^`]+)`')
CURSIVA = re.compile(r'(?<![\w*])_(.+?)_(?![\w*])')


def _linea(texto):
    t = escape(texto)
    t = CODIGO.sub(r'<code>\1</code>', t)
    t = NEGRITA.sub(r'<strong>\1</strong>', t)
    t = CURSIVA.sub(r'<em>\1</em>', t)
    # Solo rutas internas que empiezan con "/" y no con "//"
    t = ENLACE.sub(lambda m: m.group(0) if m.group(2).startswith('//')
                   else f'<a href="{m.group(2)}">{m.group(1)}</a>', t)
    return t


@register.filter
def markdown_seguro(texto):
    salida, lista = [], None
    for cruda in (texto or '').split('\n'):
        linea = cruda.rstrip()
        vineta = re.match(r'^\s*([-*•]|\d+\.)\s+(.*)$', linea)
        if vineta:
            tipo = 'ol' if vineta.group(1)[0].isdigit() else 'ul'
            if lista != tipo:
                if lista:
                    salida.append(f'</{lista}>')
                salida.append(f'<{tipo} class="mb-2">')
                lista = tipo
            salida.append(f'<li>{_linea(vineta.group(2))}</li>')
            continue
        if lista:
            salida.append(f'</{lista}>')
            lista = None
        titulo = re.match(r'^(#{1,4})\s+(.*)$', linea)
        if titulo:
            salida.append(f'<p class="fw-bold mb-1">{_linea(titulo.group(2))}</p>')
        elif linea.strip():
            salida.append(f'<p class="mb-2">{_linea(linea)}</p>')
    if lista:
        salida.append(f'</{lista}>')
    return mark_safe(''.join(salida))
