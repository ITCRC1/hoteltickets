"""
Generador único de reportes Excel: encabezado con el tipo de reporte, fecha, usuario y filtros; tabla con
encabezados de color, filtros de Excel, paneles congelados, anchos legibles y formatos de fecha/número correctos.

    columnas = [Columna('Código', 12), Columna('Adquirido', 12, 'fecha'), Columna('Monto', 14, 'dinero')]
    return respuesta_excel('Inventario', columnas, filas, request, filtros=['Estado: En uso'])
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

VERDE = '1C2A22'
DORADO = 'B8924F'
ARENA = 'F2EFE8'

FORMATOS = {
    'fecha': 'DD/MM/YYYY',
    'fechahora': 'DD/MM/YYYY HH:MM',
    'entero': '#,##0',
    'dinero': '#,##0.00',
    'porcentaje': '0.0%',
}


@dataclass
class Columna:
    titulo: str
    ancho: int = 18
    tipo: str = 'texto'  # texto | fecha | fechahora | entero | dinero | porcentaje


def _valor(v):
    """Excel no acepta fechas con zona horaria: se pasan a hora de Costa Rica sin zona."""
    if isinstance(v, datetime):
        if timezone.is_aware(v):
            v = timezone.localtime(v)
        return v.replace(tzinfo=None)
    if isinstance(v, Decimal):
        return v
    return v


def libro(titulo, columnas, filas, usuario=None, filtros=None, hoja='Datos'):
    wb = Workbook()
    ws = wb.active
    ws.title = hoja[:31]
    n = len(columnas)
    ultima = get_column_letter(n)

    # Encabezado del reporte
    ws['A1'] = f'Soporte TI · {titulo}'
    ws['A1'].font = Font(bold=True, size=14, color=VERDE)
    generado = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    por = (usuario.get_full_name() or usuario.username) if usuario is not None else ''
    ws['A2'] = f'Generado el {generado}' + (f' por {por}' if por else '') + ' · The Costa Rica Collection'
    ws['A2'].font = Font(italic=True, size=9, color='666666')
    ws['A3'] = 'Filtros: ' + ('; '.join(filtros) if filtros else 'ninguno (todos los registros)')
    ws['A3'].font = Font(size=9, color='666666')
    for fila in (1, 2, 3):
        ws.merge_cells(f'A{fila}:{ultima}{fila}')

    # Tabla
    fila_encabezado = 5
    borde = Border(bottom=Side(style='thin', color=DORADO))
    for i, col in enumerate(columnas, start=1):
        c = ws.cell(row=fila_encabezado, column=i, value=col.titulo)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor=VERDE)
        c.alignment = Alignment(vertical='center', wrap_text=True)
        c.border = borde
        ws.column_dimensions[get_column_letter(i)].width = col.ancho
    ws.row_dimensions[fila_encabezado].height = 22

    total = 0
    for total, fila in enumerate(filas, start=1):
        r = fila_encabezado + total
        for i, (col, v) in enumerate(zip(columnas, fila), start=1):
            c = ws.cell(row=r, column=i, value=_valor(v))
            if col.tipo in FORMATOS:
                c.number_format = FORMATOS[col.tipo]
            if col.tipo == 'texto':
                c.alignment = Alignment(vertical='top', wrap_text=col.ancho >= 30)
        if total % 2 == 0:
            for i in range(1, n + 1):
                ws.cell(row=r, column=i).fill = PatternFill('solid', fgColor=ARENA)

    ws.freeze_panes = ws.cell(row=fila_encabezado + 1, column=1)
    ws.auto_filter.ref = f'A{fila_encabezado}:{ultima}{fila_encabezado + max(total, 1)}'
    ws.cell(row=fila_encabezado + total + 2, column=1,
            value=f'{total} registro{"s" if total != 1 else ""}').font = Font(italic=True, size=9, color='666666')
    ws.sheet_view.zoomScale = 100
    ws.print_title_rows = f'{fila_encabezado}:{fila_encabezado}'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    return wb, total


def respuesta_excel(titulo, columnas, filas, request, filtros=None, nombre=None):
    from core.auditoria import auditar
    wb, total = libro(titulo, columnas, filas, usuario=request.user, filtros=filtros)
    buffer = BytesIO()
    wb.save(buffer)
    nombre = nombre or f'{titulo.lower().replace(" ", "_")}_{date.today():%Y-%m-%d}.xlsx'
    auditar(request, 'EXPORTADO', 'reportes', detalle=f'{titulo} · {total} registros · '
                                                       f'filtros: {"; ".join(filtros) if filtros else "ninguno"}')
    r = HttpResponse(buffer.getvalue(),
                     content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    r['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return r
