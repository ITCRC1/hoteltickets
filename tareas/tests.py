"""Pruebas de las Etapas 4 y 5: tareas (CRUD, filtros, permisos, papelera, auditoría) y calendario (4 vistas)."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import roles
from core.models import Auditoria

from .models import Tarea

CLAVE = 'clave-segura-123'


def usuario(email, rol):
    u = User.objects.create_user(username=email, email=email, password=CLAVE, first_name=email.split('@')[0])
    roles.asignar_rol(u, rol)
    return u


class Base(TestCase):
    def setUp(self):
        self.admin = usuario('admin@x.com', roles.ADMIN)
        self.it = usuario('it@x.com', roles.IT)
        self.lector = usuario('lector@x.com', roles.LECTURA)
        self.hoy = timezone.localdate()


class Tareas(Base):
    def test_crear_queda_guardada_y_auditada(self):
        self.client.force_login(self.it)
        r = self.client.post(reverse('tarea_crear'), {'titulo': 'Cambiar UPS Amarena', 'estado': 'pendiente',
                                                      'prioridad': 'alta', 'fecha_vencimiento': '2026-12-01',
                                                      'responsable': self.it.pk})
        self.assertEqual(r.status_code, 302)
        t = Tarea.objects.get()
        self.assertEqual((t.prioridad, t.fecha_vencimiento, t.responsable, t.creado_por),
                         ('alta', date(2026, 12, 1), self.it, self.it))
        self.assertTrue(Auditoria.objects.filter(modulo='tareas', accion='CREADA').exists())

    def test_titulo_obligatorio(self):
        self.client.force_login(self.it)
        r = self.client.post(reverse('tarea_crear'), {'titulo': '', 'estado': 'pendiente', 'prioridad': 'normal'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Tarea.objects.exists())

    def test_editar_audita_antes_y_despues_y_sin_cambios_no(self):
        t = Tarea.objects.create(titulo='Backup', fecha_vencimiento=self.hoy)
        self.client.force_login(self.admin)
        datos = {'titulo': 'Backup', 'estado': 'pendiente', 'prioridad': 'normal',
                 'fecha_vencimiento': self.hoy.isoformat(), 'responsable': ''}
        self.client.post(reverse('tarea_editar', args=[t.pk]), datos)
        self.assertFalse(Auditoria.objects.filter(accion='EDITADA').exists())
        self.client.post(reverse('tarea_editar', args=[t.pk]), {**datos, 'estado': 'completada'})
        t.refresh_from_db()
        self.assertEqual(t.estado, 'completada')
        self.assertIsNotNone(t.completada_en)
        self.assertEqual(Auditoria.objects.get(accion='EDITADA').cambios['estado'], ['Pendiente', 'Completada'])

    def test_cambio_rapido_de_estado(self):
        t = Tarea.objects.create(titulo='Revisar firewall')
        self.client.force_login(self.it)
        self.client.post(reverse('tarea_estado', args=[t.pk]), {'estado': 'en_progreso'})
        t.refresh_from_db()
        self.assertEqual(t.estado, 'en_progreso')

    def test_solo_lectura_consulta_pero_no_modifica(self):
        t = Tarea.objects.create(titulo='Licencias')
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(reverse('tarea_lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('tarea_editar', args=[t.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('tarea_crear')).status_code, 403)
        self.assertEqual(self.client.post(reverse('tarea_editar', args=[t.pk]), {'titulo': 'X', 'estado': 'completada',
                                                                                 'prioridad': 'baja'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('tarea_estado', args=[t.pk]), {'estado': 'completada'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('tarea_eliminar', args=[t.pk])).status_code, 403)
        t.refresh_from_db()
        self.assertEqual((t.titulo, t.estado), ('Licencias', 'pendiente'))

    def test_filtros_y_vencidas(self):
        vencida = Tarea.objects.create(titulo='Vieja', fecha_vencimiento=self.hoy - timedelta(days=3))
        Tarea.objects.create(titulo='Hecha', fecha_vencimiento=self.hoy - timedelta(days=3), estado='completada')
        hoy = Tarea.objects.create(titulo='De hoy', fecha_vencimiento=self.hoy, prioridad='urgente')
        sin = Tarea.objects.create(titulo='Sin fecha')
        self.client.force_login(self.lector)

        def ids(**p):
            return {t.pk for t in self.client.get(reverse('tarea_lista'), p).context['pagina']}
        self.assertEqual(ids(vence='vencidas'), {vencida.pk})
        self.assertEqual(ids(vence='hoy'), {hoy.pk})
        self.assertEqual(ids(vence='sin_fecha'), {sin.pk})
        self.assertEqual(ids(prioridad='urgente'), {hoy.pk})
        self.assertEqual(ids(q='vieja'), {vencida.pk})
        r = self.client.get(reverse('tarea_lista'))
        self.assertEqual(r.context['kpi']['vencidas'], 1)
        self.assertIn(hoy, list(r.context['proximas']))

    def test_papelera(self):
        t = Tarea.objects.create(titulo='Inventario de cables')
        self.client.force_login(self.it)
        self.client.post(reverse('tarea_eliminar', args=[t.pk]))
        self.assertFalse(Tarea.objects.filter(pk=t.pk).exists())
        self.assertContains(self.client.get(reverse('papelera')), 'Inventario de cables')
        self.client.post(reverse('papelera_restaurar', args=['tareas.tarea', t.pk]))
        self.assertTrue(Tarea.objects.filter(pk=t.pk).exists())


class Calendario(Base):
    def setUp(self):
        super().setUp()
        self.t = Tarea.objects.create(titulo='Mantenimiento servidor', descripcion='Cambiar discos',
                                      fecha_vencimiento=date(2026, 11, 20), prioridad='alta')
        self.client.force_login(self.lector)

    def test_vista_mensual(self):
        r = self.client.get(reverse('calendario_vista', args=['mes']), {'fecha': '2026-11-20'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Mantenimiento servidor')
        celdas = [c for sem in r.context['semanas'] for c in sem]
        self.assertEqual(len(celdas) % 7, 0)
        self.assertEqual(celdas[0]['d'].weekday(), 0)  # semanas de lunes a domingo
        self.assertEqual([t.pk for t in r.context['del_dia']], [self.t.pk])
        # el detalle viene una sola vez, en el JSON del panel
        self.assertEqual(r.context['tareas_json'][str(self.t.pk)]['descripcion'], 'Cambiar discos')

    def test_vista_semanal(self):
        r = self.client.get(reverse('calendario_vista', args=['semana']), {'fecha': '2026-11-20'})
        dias = [c['d'] for c in r.context['semanas'][0]]
        self.assertEqual((dias[0], dias[-1]), (date(2026, 11, 16), date(2026, 11, 22)))
        self.assertContains(r, 'Mantenimiento servidor')

    def test_vista_diaria(self):
        r = self.client.get(reverse('calendario_vista', args=['dia']), {'fecha': '2026-11-20'})
        self.assertEqual(r.context['resumen_dia']['pendiente'], 1)
        r = self.client.get(reverse('calendario_vista', args=['dia']), {'fecha': '2026-11-21'})
        self.assertContains(r, 'Sin tareas este día')

    def test_vista_anual(self):
        Tarea.objects.create(titulo='Otra', fecha_vencimiento=date(2026, 11, 2), estado='completada')
        r = self.client.get(reverse('calendario_vista', args=['anio']), {'fecha': '2026-03-01'})
        nov = r.context['meses'][10]
        self.assertEqual((nov['total'], nov['abiertas']), (2, 1))
        self.assertEqual(r.context['meses'][0]['total'], 0)

    def test_navegacion_entre_meses_y_fecha_invalida(self):
        r = self.client.get(reverse('calendario_vista', args=['mes']), {'fecha': '2026-01-31'})
        self.assertEqual((r.context['anterior'], r.context['siguiente']), (date(2025, 12, 1), date(2026, 2, 1)))
        self.assertEqual(self.client.get(reverse('calendario'), {'fecha': 'basura'}).status_code, 200)
        self.assertEqual(self.client.get(reverse('calendario_vista', args=['xyz'])).status_code, 200)
