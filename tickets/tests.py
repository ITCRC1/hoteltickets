"""
Pruebas de la Etapa 3: prioridad, notas de resolución, historial antes→después (sin cambios ficticios),
notas manuales, filtros/orden/paginación, departamento derivado y papelera.
"""
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core import roles
from core.models import Auditoria, Directorio

from .models import Categoria, Hotel, RegistroAuditoria, Ticket

CLAVE = 'clave-segura-123'


def usuario(email, rol):
    u = User.objects.create_user(username=email, email=email, password=CLAVE, first_name=email.split('@')[0])
    roles.asignar_rol(u, rol)
    return u


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', NOTIFICATION_EMAILS=[])
class Base(TestCase):
    def setUp(self):
        self.admin = usuario('admin@x.com', roles.ADMIN)
        self.it = usuario('it@x.com', roles.IT)
        self.lector = usuario('lector@x.com', roles.LECTURA)
        self.hotel = Hotel.objects.create(nombre='Hotel Prueba')
        self.cat = Categoria.objects.create(nombre='IT / Sistemas')

    def ticket(self, **datos):
        base = dict(titulo='PC no enciende', descripcion='x', hotel=self.hotel, categoria=self.cat,
                    solicitante_nombre='Ana', solicitante_email='ana@h.com')
        base.update(datos)
        return Ticket.objects.create(**base)

    def gestionar(self, t, **cambios):
        datos = {'accion': 'gestion', 'estado': t.estado, 'prioridad': t.prioridad, 'categoria': t.categoria_id,
                 'asignado_a': t.asignado_a_id or '', 'departamento': t.departamento,
                 'notas_resolucion': t.notas_resolucion}
        datos.update(cambios)
        return self.client.post(reverse('ticket_detalle', args=[t.pk]), datos, follow=True)


class Gestion(Base):
    def test_prioridad_por_defecto_normal_y_formulario_publico_sin_prioridad(self):
        self.assertEqual(self.ticket().prioridad, 'normal')
        r = self.client.get(reverse('ticket_publico'))
        self.assertNotContains(r, 'name="prioridad"')

    def test_historial_guarda_antes_y_despues_por_campo(self):
        t = self.ticket()
        self.client.force_login(self.it)
        self.gestionar(t, estado='en_progreso', prioridad='urgente', asignado_a=self.it.pk,
                       notas_resolucion='Se cambió la fuente de poder')
        t.refresh_from_db()
        self.assertEqual((t.estado, t.prioridad, t.asignado_a, t.notas_resolucion),
                         ('en_progreso', 'urgente', self.it, 'Se cambió la fuente de poder'))
        h = {r.accion: (r.valor_anterior, r.valor_nuevo, r.usuario) for r in t.auditoria.all()}
        self.assertEqual(h['cambio_estado'], ('Abierto', 'En progreso', self.it))
        self.assertEqual(h['cambio_prioridad'], ('Normal', 'Urgente', self.it))
        self.assertEqual(h['asignar'], ('Sin asignar', 'it', self.it))
        self.assertEqual(h['notas_resolucion'][1], 'Se cambió la fuente de poder')

    def test_guardar_sin_cambios_no_registra_nada(self):
        t = self.ticket()
        self.client.force_login(self.it)
        r = self.gestionar(t)
        self.assertContains(r, 'Sin cambios')
        self.assertFalse(t.auditoria.exists())

    def test_quitar_asignacion(self):
        t = self.ticket(asignado_a=self.it)
        self.client.force_login(self.admin)
        self.gestionar(t, asignado_a='')
        t.refresh_from_db()
        self.assertIsNone(t.asignado_a)
        self.assertTrue(t.auditoria.filter(accion='asignar', valor_nuevo='Sin asignar').exists())

    def test_resolver_marca_fecha_y_reabrir_la_limpia(self):
        t = self.ticket()
        self.client.force_login(self.it)
        self.gestionar(t, estado='resuelto')
        t.refresh_from_db()
        self.assertIsNotNone(t.resuelto_en)
        self.gestionar(t, estado='abierto')
        t.refresh_from_db()
        self.assertIsNone(t.resuelto_en)

    def test_nota_manual_al_historial(self):
        t = self.ticket()
        self.client.force_login(self.it)
        self.client.post(reverse('ticket_detalle', args=[t.pk]), {'accion': 'nota', 'nota': 'Llamé al hotel'})
        self.assertTrue(t.auditoria.filter(accion='nota', detalle='Llamé al hotel', usuario=self.it).exists())

    def test_historial_visible_en_pantalla(self):
        t = self.ticket()
        self.client.force_login(self.it)
        self.gestionar(t, prioridad='alta')
        self.client.force_login(self.lector)
        r = self.client.get(reverse('ticket_detalle', args=[t.pk]))
        self.assertContains(r, 'Cambio de prioridad')
        self.assertContains(r, 'Normal')
        self.assertNotContains(r, 'Agregar nota')  # solo lectura no agrega notas

    def test_solo_lectura_no_agrega_notas(self):
        t = self.ticket()
        self.client.force_login(self.lector)
        r = self.client.post(reverse('ticket_detalle', args=[t.pk]), {'accion': 'nota', 'nota': 'x'})
        self.assertEqual(r.status_code, 403)


class Departamento(Base):
    def test_se_deriva_del_directorio(self):
        Directorio.objects.create(email='Ana@H.com', departamento='Recepción')
        self.assertEqual(self.ticket().departamento, 'Recepción')

    def test_se_deriva_del_perfil_de_usuario(self):
        from core.invitaciones import perfil_de
        perfil = perfil_de(self.it)
        perfil.departamento = 'Sistemas'
        perfil.save()
        self.assertEqual(self.ticket(solicitante_email='IT@x.com').departamento, 'Sistemas')

    def test_sin_coincidencia_queda_vacio(self):
        self.assertEqual(self.ticket(solicitante_email='nadie@h.com').departamento, '')

    def test_desde_el_formulario_publico(self):
        Directorio.objects.create(email='ana@h.com', departamento='Cocina')
        self.client.post(reverse('ticket_publico'), {'hotel': self.hotel.pk, 'titulo': 'Impresora no funciona',
                                                     'descripcion': 'No imprime', 'solicitante_nombre': 'Ana',
                                                     'solicitante_email': 'ana@h.com'})
        self.assertEqual(Ticket.objects.get().departamento, 'Cocina')


class Lista(Base):
    def setUp(self):
        super().setUp()
        self.t_urgente = self.ticket(titulo='Servidor caído', prioridad='urgente', asignado_a=self.it)
        self.t_baja = self.ticket(titulo='Mouse', prioridad='baja', estado='resuelto')
        self.t_normal = self.ticket(titulo='Correo lento', solicitante_email='beto@h.com')
        self.client.force_login(self.lector)

    def ids(self, **params):
        r = self.client.get(reverse('ticket_lista'), params)
        return [t.pk for t in r.context['pagina']], r

    def test_filtros(self):
        self.assertEqual(self.ids(prioridad='urgente')[0], [self.t_urgente.pk])
        self.assertEqual(self.ids(asignado=self.it.pk)[0], [self.t_urgente.pk])
        self.assertEqual(set(self.ids(asignado='ninguno')[0]), {self.t_baja.pk, self.t_normal.pk})
        self.assertEqual(set(self.ids(estado='abiertos')[0]), {self.t_urgente.pk, self.t_normal.pk})
        self.assertEqual(self.ids(q='beto@')[0], [self.t_normal.pk])
        self.assertEqual(self.ids(q=f'#{self.t_baja.pk}')[0], [self.t_baja.pk])

    def test_contador_y_limpiar(self):
        _, r = self.ids(prioridad='urgente')
        self.assertEqual(r.context['total'], 1)
        self.assertContains(r, '1 ticket con estos filtros')
        self.assertTrue(r.context['hay_filtros'])
        self.assertFalse(self.ids()[1].context['hay_filtros'])

    def test_ordenes(self):
        self.assertEqual(self.ids(orden='prioridad')[0][0], self.t_urgente.pk)
        self.assertEqual(self.ids(orden='prioridad')[0][-1], self.t_baja.pk)
        self.assertEqual(self.ids(orden='pendientes')[0][-1], self.t_baja.pk)
        self.assertEqual(self.ids(orden='finalizados')[0][0], self.t_baja.pk)
        self.assertEqual(self.ids(orden='antiguos')[0][0], self.t_urgente.pk)

    def test_paginacion(self):
        for i in range(30):
            self.ticket(titulo=f'T{i}')
        ids1, r = self.ids()
        self.assertEqual(len(ids1), 25)
        self.assertEqual(r.context['total'], 33)
        ids2, _ = self.ids(page=2)
        self.assertEqual(len(ids2), 8)
        self.assertFalse(set(ids1) & set(ids2))

    def test_parametros_basura_no_rompen(self):
        self.assertEqual(self.ids(hotel='abc', asignado='x', orden='nada', page='zz')[1].status_code, 200)


class Papelera(Base):
    def test_it_envia_a_papelera_y_desaparece_de_lista_y_dashboard(self):
        t = self.ticket()
        self.client.force_login(self.it)
        self.client.post(reverse('ticket_eliminar', args=[t.pk]), {'motivo': 'Duplicado'})
        t = Ticket.todos.get(pk=t.pk)
        self.assertTrue(t.en_papelera)
        self.assertEqual(t.eliminado_por, self.it)
        self.assertFalse(Ticket.objects.filter(pk=t.pk).exists())
        self.assertEqual(self.client.get(reverse('dashboard')).context['total'], 0)
        self.assertTrue(RegistroAuditoria.objects.filter(ticket=t, accion='eliminar', detalle='Duplicado').exists())
        self.assertTrue(Auditoria.objects.filter(accion='ENVIADO_A_PAPELERA').exists())
        self.assertContains(self.client.get(reverse('papelera')), 'PC no enciende')

    def test_solo_lectura_no_elimina_ni_ve_papelera(self):
        t = self.ticket()
        self.client.force_login(self.lector)
        self.assertEqual(self.client.post(reverse('ticket_eliminar', args=[t.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('papelera')).status_code, 403)
        self.assertFalse(Ticket.todos.get(pk=t.pk).en_papelera)

    def test_restaurar(self):
        t = self.ticket()
        t.enviar_a_papelera(self.admin)
        self.client.force_login(self.it)
        self.client.post(reverse('papelera_restaurar', args=['tickets.ticket', t.pk]))
        self.assertTrue(Ticket.objects.filter(pk=t.pk).exists())
        self.assertTrue(t.auditoria.filter(accion='restaurar').exists())

    def test_borrado_definitivo_solo_admin(self):
        t = self.ticket()
        t.enviar_a_papelera(self.admin)
        self.client.force_login(self.it)
        self.assertEqual(self.client.post(reverse('papelera_purgar', args=['tickets.ticket', t.pk])).status_code, 403)
        self.assertTrue(Ticket.todos.filter(pk=t.pk).exists())
        self.client.force_login(self.admin)
        self.client.post(reverse('papelera_purgar', args=['tickets.ticket', t.pk]))
        self.assertFalse(Ticket.todos.filter(pk=t.pk).exists())
        a = Auditoria.objects.get(accion='ELIMINADO_DEFINITIVO')
        self.assertIn('PC no enciende', a.detalle)  # queda constancia de qué se borró

    def test_no_se_purga_lo_que_no_esta_en_papelera(self):
        t = self.ticket()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('papelera_purgar', args=['tickets.ticket', t.pk])).status_code, 404)
        self.assertTrue(Ticket.objects.filter(pk=t.pk).exists())

    def test_ticket_en_papelera_no_se_modifica(self):
        t = self.ticket()
        t.enviar_a_papelera(self.admin)
        self.client.force_login(self.it)
        self.gestionar(t, estado='cerrado')
        self.assertEqual(Ticket.todos.get(pk=t.pk).estado, 'abierto')

    def test_solo_lectura_no_ve_tickets_en_papelera(self):
        t = self.ticket()
        t.enviar_a_papelera(self.admin)
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(reverse('ticket_detalle', args=[t.pk])).status_code, 404)
