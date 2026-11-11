"""Pruebas de la Etapa 7: exportaciones a Excel (contenido, filtros, formatos, papelera, permisos, auditoría)."""
from datetime import date, datetime
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from core import roles
from core.models import Auditoria
from inventario.models import Activo, CategoriaActivo, EstadoActivo
from tareas.models import Tarea
from tickets.models import Categoria, Hotel, Ticket

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
FILA_ENCABEZADO = 5


def usuario(email, rol):
    u = User.objects.create_user(username=email, email=email, password='clave-segura-123', first_name='Ana', last_name='Soto')
    roles.asignar_rol(u, rol)
    return u


def hoja(respuesta):
    return load_workbook(BytesIO(respuesta.content)).active


def filas(ws):
    """Filas de datos (debajo del encabezado), hasta la primera vacía."""
    salida = []
    for fila in ws.iter_rows(min_row=FILA_ENCABEZADO + 1, values_only=True):
        if fila[0] is None:
            break
        salida.append(fila)
    return salida


class Exportaciones(TestCase):
    def setUp(self):
        self.lector = usuario('lector@x.com', roles.LECTURA)
        self.hotel = Hotel.objects.create(nombre='Hotel Amarena Beach')
        cat = Categoria.objects.create(nombre='IT / Sistemas')
        self.t1 = Ticket.objects.create(titulo='Servidor caído', descripcion='x', hotel=self.hotel, categoria=cat,
                                        prioridad='urgente', solicitante_nombre='Ana', solicitante_email='ana@h.com')
        self.t2 = Ticket.objects.create(titulo='Mouse', descripcion='y', hotel=self.hotel, categoria=cat,
                                        solicitante_nombre='Beto', solicitante_email='b@h.com')
        borrado = Ticket.objects.create(titulo='Duplicado', descripcion='z', hotel=self.hotel, categoria=cat,
                                        solicitante_nombre='C', solicitante_email='c@h.com')
        borrado.enviar_a_papelera(self.lector)
        self.activo = Activo.objects.create(codigo='LAP-1', nombre='Laptop', categoria=CategoriaActivo.objects.get(nombre='Laptops'),
                                            ubicacion=self.hotel, estado=EstadoActivo.objects.get(nombre='En uso'),
                                            fecha_adquisicion=date(2025, 3, 15))
        Tarea.objects.create(titulo='Backup', fecha_vencimiento=date(2026, 12, 1))
        self.client.force_login(self.lector)

    def test_tickets_excel_completo(self):
        r = self.client.get(reverse('exportar_tickets'))
        self.assertEqual(r['Content-Type'], XLSX)
        self.assertIn('attachment; filename="tickets_', r['Content-Disposition'])
        ws = hoja(r)
        self.assertIn('Tickets', ws['A1'].value)
        self.assertIn('Ana Soto', ws['A2'].value)
        encabezados = [c.value for c in ws[FILA_ENCABEZADO]]
        self.assertEqual(encabezados[:3], ['#', 'Título', 'Ubicación'])
        datos = filas(ws)
        self.assertEqual({d[1] for d in datos}, {'Servidor caído', 'Mouse'})  # sin lo de la papelera
        self.assertEqual(ws.auto_filter.ref.split(':')[0], f'A{FILA_ENCABEZADO}')
        self.assertEqual(ws.freeze_panes, f'A{FILA_ENCABEZADO + 1}')
        creado = ws.cell(row=FILA_ENCABEZADO + 1, column=11)
        self.assertIsInstance(creado.value, datetime)
        self.assertEqual(creado.number_format, 'DD/MM/YYYY HH:MM')

    def test_respeta_los_filtros_de_la_lista(self):
        ws = hoja(self.client.get(reverse('exportar_tickets'), {'prioridad': 'urgente'}))
        self.assertEqual([d[1] for d in filas(ws)], ['Servidor caído'])
        self.assertIn('Prioridad: Urgente', ws['A3'].value)

    def test_inventario_con_fechas(self):
        ws = hoja(self.client.get(reverse('exportar_inventario')))
        fila = filas(ws)[0]
        self.assertEqual(fila[0], 'LAP-1')
        celda = ws.cell(row=FILA_ENCABEZADO + 1, column=11)
        self.assertEqual(celda.value.date(), date(2025, 3, 15))
        self.assertEqual(celda.number_format, 'DD/MM/YYYY')

    def test_tareas(self):
        ws = hoja(self.client.get(reverse('exportar_tareas')))
        self.assertEqual(filas(ws)[0][0], 'Backup')

    def test_queda_en_auditoria(self):
        self.client.get(reverse('exportar_inventario'), {'q': 'lap'})
        a = Auditoria.objects.get(accion='EXPORTADO')
        self.assertIn('Inventario · 1 registros', a.detalle)
        self.assertIn('Búsqueda: lap', a.detalle)

    def test_requiere_login_y_rol(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('exportar_tickets')).status_code, 302)
        sin_rol = User.objects.create_user(username='n@x.com', email='n@x.com', password='clave-segura-123')
        self.client.force_login(sin_rol)
        self.assertEqual(self.client.get(reverse('exportar_tickets')).status_code, 403)

    def test_pagina_de_reportes(self):
        r = self.client.get(reverse('reportes'))
        self.assertEqual(r.context['conteos'], {'inventario': 1, 'tickets': 2, 'tareas': 1, 'gastos': 0, 'suscripciones': 0})

    def test_lista_vacia_genera_excel_valido(self):
        ws = hoja(self.client.get(reverse('exportar_tickets'), {'q': 'no-existe-nada'}))
        self.assertEqual(filas(ws), [])
