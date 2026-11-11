"""Pruebas de la Etapa 6: inventario (registro, código automático, validaciones, filtros, estadísticas, permisos, papelera)."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import roles
from core.models import Auditoria
from tickets.models import Hotel

from .models import Activo, CategoriaActivo, EstadoActivo


def usuario(email, rol):
    u = User.objects.create_user(username=email, email=email, password='clave-segura-123')
    roles.asignar_rol(u, rol)
    return u


class Base(TestCase):
    def setUp(self):
        self.admin = usuario('admin@x.com', roles.ADMIN)
        self.it = usuario('it@x.com', roles.IT)
        self.lector = usuario('lector@x.com', roles.LECTURA)
        self.amarena = Hotel.objects.create(nombre='Hotel Amarena Beach')
        self.uvita = Hotel.objects.create(nombre='Oficina Uvita', tipo='punto_externo')
        self.laptop = CategoriaActivo.objects.get(nombre='Laptops')
        self.ups = CategoriaActivo.objects.get(nombre='UPS')
        self.en_uso = EstadoActivo.objects.get(nombre='En uso')
        self.danado = EstadoActivo.objects.get(nombre='Dañado')
        self.hoy = timezone.localdate()

    def datos(self, **extra):
        d = {'codigo': '', 'nombre': 'Laptop recepción', 'categoria': self.laptop.pk, 'marca': 'Dell',
             'modelo': 'Latitude 5440', 'numero_serie': 'ABC123', 'ubicacion': self.amarena.pk,
             'departamento': 'Recepción', 'responsable': 'María', 'estado': self.en_uso.pk,
             'fecha_adquisicion': '2025-01-10', 'garantia_hasta': '2027-01-10', 'observaciones': ''}
        d.update(extra)
        return d

    def activo(self, **extra):
        base = dict(nombre='Equipo', categoria=self.laptop, ubicacion=self.amarena, estado=self.en_uso)
        base.update(extra)
        return Activo.objects.create(**base)


class Catalogos(TestCase):
    def test_categorias_y_estados_sembrados(self):
        nombres = set(CategoriaActivo.objects.values_list('nombre', flat=True))
        for c in ('Computadoras', 'Laptops', 'Tablets', 'Impresoras', 'Routers', 'Switches', 'Puntos de acceso',
                  'Servidores', 'Cámaras', 'UPS', 'Periféricos', 'Otros'):
            self.assertIn(c, nombres)
        self.assertEqual(EstadoActivo.objects.count(), 5)


class Registro(Base):
    def test_registrar_con_codigo_automatico_y_auditoria(self):
        self.client.force_login(self.it)
        self.client.post(reverse('activo_crear'), self.datos())
        a = Activo.objects.get()
        self.assertEqual(a.codigo, f'TI-{a.pk:05d}')
        self.assertEqual((a.marca, a.ubicacion, a.creado_por), ('Dell', self.amarena, self.it))
        self.assertTrue(Auditoria.objects.filter(modulo='inventario', accion='CREADO').exists())

    def test_codigo_manual_unico_incluso_contra_papelera(self):
        viejo = self.activo(codigo='LAP-001')
        viejo.enviar_a_papelera(self.admin)
        self.client.force_login(self.it)
        r = self.client.post(reverse('activo_crear'), self.datos(codigo='lap-001'))
        self.assertContains(r, 'Ya existe un activo con ese código')
        self.assertEqual(Activo.todos.count(), 1)

    def test_garantia_antes_de_adquisicion(self):
        self.client.force_login(self.it)
        r = self.client.post(reverse('activo_crear'), self.datos(garantia_hasta='2024-01-01'))
        self.assertContains(r, 'no puede vencer antes')
        self.assertFalse(Activo.objects.exists())

    def test_editar_audita_cambios(self):
        a = self.activo(codigo='UPS-01', categoria=self.ups)
        self.client.force_login(self.admin)
        self.client.post(reverse('activo_editar', args=[a.pk]),
                         self.datos(codigo='UPS-01', categoria=self.ups.pk, estado=self.danado.pk, nombre='UPS rack'))
        a.refresh_from_db()
        self.assertEqual(a.estado, self.danado)
        cambios = Auditoria.objects.get(accion='EDITADO').cambios
        self.assertEqual(cambios['estado'], ['En uso', 'Dañado'])

    def test_solo_lectura(self):
        a = self.activo(codigo='X1')
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(reverse('activo_lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('activo_editar', args=[a.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('activo_crear')).status_code, 403)
        self.assertEqual(self.client.post(reverse('activo_editar', args=[a.pk]), self.datos(codigo='X1')).status_code, 403)
        self.assertEqual(self.client.post(reverse('activo_eliminar', args=[a.pk])).status_code, 403)

    def test_papelera(self):
        a = self.activo(codigo='CAM-9', categoria=CategoriaActivo.objects.get(nombre='Cámaras'))
        self.client.force_login(self.it)
        self.client.post(reverse('activo_eliminar', args=[a.pk]))
        self.assertFalse(Activo.objects.filter(pk=a.pk).exists())
        self.assertContains(self.client.get(reverse('papelera')), 'CAM-9')


class ListaYEstadisticas(Base):
    def setUp(self):
        super().setUp()
        self.a1 = self.activo(codigo='L1', nombre='Laptop gerencia', marca='Lenovo', departamento='Gerencia',
                              garantia_hasta=self.hoy + timedelta(days=30))
        self.a2 = self.activo(codigo='U1', nombre='UPS servidor', categoria=self.ups, ubicacion=self.uvita,
                              estado=self.danado, numero_serie='SN-777', garantia_hasta=self.hoy - timedelta(days=1))
        self.a3 = self.activo(codigo='L2', nombre='Laptop bodega')
        self.client.force_login(self.lector)

    def ids(self, **p):
        return [a.pk for a in self.client.get(reverse('activo_lista'), p).context['pagina']]

    def test_busqueda_y_filtros(self):
        self.assertEqual(self.ids(q='sn-777'), [self.a2.pk])
        self.assertEqual(self.ids(q='lenovo'), [self.a1.pk])
        self.assertEqual(self.ids(categoria=self.ups.pk), [self.a2.pk])
        self.assertEqual(self.ids(ubicacion=self.uvita.pk), [self.a2.pk])
        self.assertEqual(self.ids(estado=self.danado.pk), [self.a2.pk])
        self.assertEqual(self.ids(departamento='Gerencia'), [self.a1.pk])
        self.assertEqual(self.ids(garantia='por_vencer'), [self.a1.pk])
        self.assertEqual(self.ids(garantia='vencida'), [self.a2.pk])
        self.assertEqual(self.ids(garantia='sin'), [self.a3.pk])

    def test_orden(self):
        self.assertEqual(self.ids(orden='garantia')[0], self.a2.pk)
        self.assertEqual(self.ids(orden='nombre')[-1], self.a2.pk)

    def test_estadisticas(self):
        stats = self.client.get(reverse('activo_lista')).context['stats']
        self.assertEqual(stats['total'], 3)
        self.assertEqual({c['categoria__nombre']: c['n'] for c in stats['por_categoria']}, {'Laptops': 2, 'UPS': 1})
        self.assertEqual((stats['garantia_vencida'], stats['garantia_por_vencer']), (1, 1))

    def test_estado_garantia(self):
        self.assertEqual((self.a1.estado_garantia, self.a2.estado_garantia, self.a3.estado_garantia),
                         ('por_vencer', 'vencida', ''))
