"""
Pruebas de las Etapas 9 y 10: presupuestos, gastos, tipo de cambio mensual y suscripciones.
Foco: precisión decimal, conversión explícita CRC↔USD, nada se suma sin tipo de cambio, permisos.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from core import roles
from core.models import Auditoria

from .calculos import renovaciones, resumen_anual, sumar_meses
from .models import CRC, USD, CategoriaGasto, Gasto, Presupuesto, Suscripcion, TipoCambio, convertir

D = Decimal


def usuario(email, rol):
    u = User.objects.create_user(username=email, email=email, password='clave-segura-123')
    roles.asignar_rol(u, rol)
    return u


class Base(TestCase):
    def setUp(self):
        self.admin = usuario('admin@x.com', roles.ADMIN)
        self.it = usuario('it@x.com', roles.IT)
        self.lector = usuario('lector@x.com', roles.LECTURA)
        self.hardware = CategoriaGasto.objects.get(nombre='Hardware')
        self.licencias = CategoriaGasto.objects.get(nombre='Licencias')


class Conversion(TestCase):
    def test_conversion_explicita_y_redondeo(self):
        self.assertEqual(convertir(D('1000.00'), USD, USD, None), D('1000.00'))
        self.assertEqual(convertir(D('100'), USD, CRC, D('505.5')), D('50550.00'))
        self.assertEqual(convertir(D('10000'), CRC, USD, D('3')), D('3333.33'))
        self.assertEqual(convertir(D('0.005'), USD, USD, None), D('0.01'))  # ROUND_HALF_UP
        self.assertIsNone(convertir(D('100'), CRC, USD, None))  # sin tipo NO se convierte

    def test_un_tipo_por_mes_y_promedio(self):
        TipoCambio.objects.create(anio=2026, mes=1, crc_por_usd=D('500'))
        TipoCambio.objects.create(anio=2026, mes=2, crc_por_usd=D('510'))
        self.assertEqual(TipoCambio.del_mes(2026, 2), D('510'))
        self.assertIsNone(TipoCambio.del_mes(2026, 3))
        self.assertEqual(TipoCambio.promedio_del_anio(2026), D('505.0000'))
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            TipoCambio.objects.create(anio=2026, mes=1, crc_por_usd=D('600'))


class Resumen(Base):
    def setUp(self):
        super().setUp()
        TipoCambio.objects.create(anio=2026, mes=1, crc_por_usd=D('500'))
        TipoCambio.objects.create(anio=2026, mes=2, crc_por_usd=D('520'))
        Presupuesto.objects.create(anio=2026, categoria=self.hardware, monto=D('12000'), moneda=USD)
        Presupuesto.objects.create(anio=2026, categoria=self.licencias, monto=D('1020000'), moneda=CRC)  # ÷ 510 prom = 2000
        Gasto.objects.create(fecha=date(2026, 1, 15), concepto='Laptops', categoria=self.hardware, monto=D('3000'), moneda=USD)
        Gasto.objects.create(fecha=date(2026, 2, 10), concepto='Switch', categoria=self.hardware, monto=D('260000'),
                             moneda=CRC, estado='pendiente')  # ÷ 520 = 500
        Gasto.objects.create(fecha=date(2026, 2, 11), concepto='Anulado', categoria=self.hardware, monto=D('999'),
                             moneda=USD, estado='anulado')
        Gasto.objects.create(fecha=date(2026, 3, 5), concepto='Sin tipo', categoria=self.licencias, monto=D('50000'), moneda=CRC)

    def test_totales_en_usd_sin_mezclar_monedas(self):
        r = resumen_anual(2026, USD, date(2026, 3, 31))
        hw = next(c for c in r['categorias'] if c['categoria'] == self.hardware)
        lic = next(c for c in r['categorias'] if c['categoria'] == self.licencias)
        self.assertEqual(hw['asignado'], D('12000.00'))
        self.assertEqual(hw['utilizado'], D('3500.00'))  # 3000 + 260000/520, sin el anulado
        self.assertEqual((hw['pagado'], hw['pendiente']), (D('3000.00'), D('500.00')))
        self.assertEqual(hw['disponible'], D('8500.00'))
        self.assertEqual(lic['asignado'], D('2000.00'))
        self.assertEqual(lic['utilizado'], D('0.00'))  # el gasto de marzo no tiene tipo → fuera
        self.assertEqual([g.concepto for g in r['sin_tipo']], ['Sin tipo'])
        self.assertEqual(r['total']['asignado'], D('14000.00'))
        self.assertEqual(r['total']['utilizado'], D('3500.00'))

    def test_proyeccion_y_por_mes(self):
        r = resumen_anual(2026, USD, date(2026, 3, 31))
        self.assertEqual(r['meses_transcurridos'], 3)
        hw = next(c for c in r['categorias'] if c['categoria'] == self.hardware)
        self.assertEqual(hw['proyeccion'], D('14000.00'))  # 3500 / 3 * 12
        self.assertTrue(hw['excede'])
        self.assertEqual([m['monto'] for m in r['por_mes'][:3]], [D('3000.00'), D('500.00'), D('0.00')])

    def test_en_colones(self):
        r = resumen_anual(2026, CRC, date(2026, 3, 31))
        hw = next(c for c in r['categorias'] if c['categoria'] == self.hardware)
        self.assertEqual(hw['utilizado'], D('1760000.00'))  # 3000*500 + 260000
        self.assertEqual(r['sin_tipo'], [])  # en CRC el gasto en colones no necesita tipo

    def test_gasto_se_asocia_solo_al_presupuesto(self):
        g = Gasto.objects.get(concepto='Laptops')
        self.assertEqual(g.presupuesto, Presupuesto.objects.get(anio=2026, categoria=self.hardware))

    def test_pantalla_avisa_lo_que_no_suma(self):
        self.client.force_login(self.lector)
        r = self.client.get(reverse('presupuesto_resumen'), {'anio': 2026})
        self.assertContains(r, 'Faltan tipos de cambio')
        self.assertContains(r, '1 gasto')


class Permisos(Base):
    def test_solo_admin_registra(self):
        datos = {'anio': 2026, 'categoria': self.hardware.pk, 'monto': '5000', 'moneda': USD, 'observaciones': ''}
        for u in (self.it, self.lector):
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse('presupuesto_crear')).status_code, 403)
            self.assertEqual(self.client.post(reverse('presupuesto_crear'), datos).status_code, 403)
            self.assertEqual(self.client.post(reverse('tipos_cambio'), {'anio': 2026, 'mes': 1, 'crc_por_usd': '500'}).status_code, 403)
        self.assertFalse(Presupuesto.objects.exists())
        self.client.force_login(self.admin)
        self.client.post(reverse('presupuesto_crear'), datos)
        self.assertEqual(Presupuesto.objects.get().monto, D('5000.00'))
        self.assertTrue(Auditoria.objects.filter(modulo='presupuesto', accion='CREADO').exists())

    def test_todos_consultan(self):
        p = Presupuesto.objects.create(anio=2026, categoria=self.hardware, monto=D('1'), moneda=USD)
        for u in (self.it, self.lector):
            self.client.force_login(u)
            for nombre in ('presupuesto_resumen', 'gasto_lista', 'suscripcion_lista', 'tipos_cambio'):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, (u, nombre))
            self.assertEqual(self.client.get(reverse('presupuesto_editar', args=[p.pk])).status_code, 200)
            self.assertEqual(self.client.post(reverse('presupuesto_editar', args=[p.pk]), {}).status_code, 403)

    def test_presupuesto_duplicado(self):
        Presupuesto.objects.create(anio=2026, categoria=self.hardware, monto=D('1'), moneda=USD)
        self.client.force_login(self.admin)
        r = self.client.post(reverse('presupuesto_crear'), {'anio': 2026, 'categoria': self.hardware.pk, 'monto': '9',
                                                            'moneda': USD})
        self.assertContains(r, 'Ya existe un presupuesto 2026')
        self.assertEqual(Presupuesto.objects.count(), 1)

    def test_tipo_de_cambio_se_reemplaza_y_audita(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('tipos_cambio'), {'anio': 2026, 'mes': 5, 'crc_por_usd': '505.25'})
        self.client.post(reverse('tipos_cambio'), {'anio': 2026, 'mes': 5, 'crc_por_usd': '506.00'})
        self.assertEqual(TipoCambio.objects.get(anio=2026, mes=5).crc_por_usd, D('506.0000'))
        self.assertEqual(Auditoria.objects.filter(modulo='tipo_cambio', accion='EDITADO').get().cambios['crc_por_usd'],
                         ['505.2500', '506.0000'])

    def test_gasto_papelera_y_edicion(self):
        g = Gasto.objects.create(fecha=date(2026, 4, 1), concepto='Mouse', categoria=self.hardware, monto=D('20'), moneda=USD)
        self.client.force_login(self.admin)
        self.client.post(reverse('gasto_editar', args=[g.pk]), {'fecha': '2026-04-01', 'concepto': 'Mouse', 'categoria': self.hardware.pk,
                                                                'monto': '25.50', 'moneda': USD, 'estado': 'pagado'})
        g.refresh_from_db()
        self.assertEqual(g.monto, D('25.50'))
        self.client.post(reverse('gasto_eliminar', args=[g.pk]))
        self.assertFalse(Gasto.objects.filter(pk=g.pk).exists())
        self.assertContains(self.client.get(reverse('papelera')), 'Mouse')

    def test_gasto_monto_debe_ser_positivo(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('gasto_crear'), {'fecha': '2026-04-01', 'concepto': 'X', 'categoria': self.hardware.pk,
                                                  'monto': '-5', 'moneda': USD, 'estado': 'pagado'})
        self.assertFalse(Gasto.objects.exists())


class Suscripciones(Base):
    def setUp(self):
        super().setUp()
        self.m365 = Suscripcion.objects.create(nombre='Microsoft 365', proveedor='Microsoft', categoria=self.licencias,
                                               costo=D('120.00'), moneda=USD, frecuencia='mensual',
                                               proxima_renovacion=date(2026, 11, 20))
        self.dominio = Suscripcion.objects.create(nombre='Dominio', proveedor='GoDaddy', categoria=self.licencias,
                                                  costo=D('30.00'), moneda=USD, frecuencia='anual',
                                                  proxima_renovacion=date(2027, 3, 1))

    def test_costos_mensual_y_anual(self):
        self.assertEqual((self.m365.costo_mensual, self.m365.costo_anual), (D('120.00'), D('1440.00')))
        self.assertEqual((self.dominio.costo_mensual, self.dominio.costo_anual), (D('2.50'), D('30.00')))
        t = Suscripcion(costo=D('100'), frecuencia='trimestral')
        self.assertEqual((t.costo_mensual, t.costo_anual), (D('33.33'), D('400.00')))

    def test_renovaciones(self):
        fechas = renovaciones(self.m365, date(2026, 11, 1), date(2027, 2, 28))
        self.assertEqual(fechas, [date(2026, 11, 20), date(2026, 12, 20), date(2027, 1, 20), date(2027, 2, 20)])
        self.assertEqual(sumar_meses(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.m365.estado = 'cancelada'
        self.assertEqual(renovaciones(self.m365, date(2026, 1, 1), date(2027, 1, 1)), [])

    def test_lista_kpis_y_proyeccion(self):
        self.client.force_login(self.lector)
        r = self.client.get(reverse('suscripcion_lista'))
        self.assertEqual(r.context['kpi']['mensual'], D('122.50'))
        self.assertEqual(r.context['kpi']['anual'], D('1470.00'))
        self.assertEqual(len(r.context['proyeccion']), 12)

    def test_registrar_pago_crea_gasto_y_adelanta_renovacion(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('suscripcion_pagar', args=[self.m365.pk]))
        g = Gasto.objects.get(suscripcion=self.m365)
        self.assertEqual((g.fecha, g.monto, g.moneda, g.estado, g.categoria), (date(2026, 11, 20), D('120.00'), USD, 'pagado', self.licencias))
        self.m365.refresh_from_db()
        self.assertEqual(self.m365.proxima_renovacion, date(2026, 12, 20))

    def test_solo_admin_registra_pagos(self):
        self.client.force_login(self.it)
        self.assertEqual(self.client.post(reverse('suscripcion_pagar', args=[self.m365.pk])).status_code, 403)
        self.assertFalse(Gasto.objects.exists())

    def test_activa_requiere_renovacion(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('suscripcion_crear'), {'nombre': 'X', 'categoria': self.licencias.pk, 'costo': '10',
                                                            'moneda': USD, 'frecuencia': 'mensual', 'estado': 'activa'})
        self.assertContains(r, 'necesita su próxima renovación')

    def test_relacion_con_presupuesto(self):
        r = resumen_anual(2026, USD, date(2026, 11, 11))
        lic = next(c for c in r['categorias'] if c['categoria'] == self.licencias)
        self.assertEqual(lic['suscripciones'], D('240.00'))  # nov y dic de M365; el dominio renueva en 2027


class Exportaciones(Base):
    def test_excel_de_presupuesto_gastos_y_suscripciones(self):
        Presupuesto.objects.create(anio=2026, categoria=self.hardware, monto=D('1000'), moneda=USD)
        Gasto.objects.create(fecha=date(2026, 1, 2), concepto='Disco', categoria=self.hardware, monto=D('100'), moneda=USD)
        Suscripcion.objects.create(nombre='Zoom', categoria=self.licencias, costo=D('15'), moneda=USD,
                                   proxima_renovacion=date(2026, 12, 1))
        self.client.force_login(self.lector)
        for nombre, params, esperado in (('exportar_presupuesto', {'anio': 2026}, 'Hardware'),
                                         ('exportar_gastos', {}, 'Disco'), ('exportar_suscripciones', {}, 'Zoom')):
            r = self.client.get(reverse(nombre), params)
            ws = load_workbook(BytesIO(r.content)).active
            self.assertIn(esperado, [c.value for c in ws[6]], nombre)
