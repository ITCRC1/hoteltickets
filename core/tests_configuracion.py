"""Pruebas de la Etapa 12: configuración (catálogos, directorio, destinatarios de avisos, permisos)."""
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from tickets.models import Categoria, Hotel, Ticket

from . import roles
from .models import Auditoria, Directorio, Parametro, destinatarios_avisos


def usuario(email, rol):
    u = User.objects.create_user(username=email, email=email, password='clave-segura-123')
    roles.asignar_rol(u, rol)
    return u


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', NOTIFICATION_EMAILS=['viejo@x.com'],
                   BREVO_API_KEY='')
class Configuracion(TestCase):
    def setUp(self):
        self.admin = usuario('admin@x.com', roles.ADMIN)
        self.it = usuario('it@x.com', roles.IT)
        self.client.force_login(self.admin)

    def test_solo_admin(self):
        self.client.force_login(self.it)
        self.assertEqual(self.client.get(reverse('configuracion')).status_code, 403)
        self.assertEqual(self.client.get(reverse('catalogo', args=['ubicaciones'])).status_code, 403)
        self.assertEqual(self.client.post(reverse('catalogo', args=['directorio']),
                                          {'email': 'a@b.com', 'departamento': 'X'}).status_code, 403)

    def test_destinatarios_usa_railway_hasta_configurarse(self):
        self.assertEqual(destinatarios_avisos(), ['viejo@x.com'])
        self.client.post(reverse('configuracion'), {'destinatarios_avisos': 'IT@x.com; finance@x.com, it@x.com'})
        self.assertEqual(destinatarios_avisos(), ['it@x.com', 'finance@x.com'])
        cambios = Auditoria.objects.get(modulo='configuracion').cambios['destinatarios_avisos']
        self.assertEqual(cambios, ['viejo@x.com', 'it@x.com, finance@x.com'])

    def test_correo_invalido_no_se_guarda(self):
        r = self.client.post(reverse('configuracion'), {'destinatarios_avisos': 'bien@x.com, mal-correo'})
        self.assertContains(r, 'Correos no válidos: mal-correo')
        self.assertFalse(Parametro.objects.exists())

    def test_los_avisos_salen_a_la_lista_configurada(self):
        self.client.post(reverse('configuracion'), {'destinatarios_avisos': 'nuevo@x.com'})
        hotel = Hotel.objects.create(nombre='Hotel A')
        self.client.logout()
        self.client.post(reverse('ticket_publico'), {'hotel': hotel.pk, 'titulo': 'Impresora no funciona',
                                                     'descripcion': 'x', 'solicitante_nombre': 'Ana',
                                                     'solicitante_email': 'ana@h.com'})
        self.assertTrue(Ticket.objects.exists())
        destinatarios = [m.to for m in mail.outbox]
        self.assertIn(['nuevo@x.com'], destinatarios)
        self.assertNotIn(['viejo@x.com'], destinatarios)

    def test_catalogo_alta_y_edicion_auditadas(self):
        self.client.post(reverse('catalogo', args=['ubicaciones']), {'nombre': 'Oficina Drake', 'tipo': 'punto_externo',
                                                                     'activo': 'on'})
        h = Hotel.objects.get(nombre='Oficina Drake')
        self.assertEqual(h.tipo, 'punto_externo')
        self.client.post(reverse('catalogo_editar', args=['ubicaciones', h.pk]), {'nombre': 'Oficina Drake', 'tipo': 'punto_externo'})
        h.refresh_from_db()
        self.assertFalse(h.activo)  # desactivada, no borrada
        self.assertEqual(Auditoria.objects.get(accion='EDITADO').cambios['activo'], ['sí', 'no'])

    def test_categoria_ticket_con_color(self):
        self.client.post(reverse('catalogo', args=['categorias-tickets']), {'nombre': 'Redes', 'color': '#2e8b86', 'activa': 'on'})
        self.assertEqual(Categoria.objects.get(nombre='Redes').color, '#2e8b86')
        self.assertContains(self.client.get(reverse('catalogo', args=['categorias-tickets'])), 'type="color"')

    def test_directorio_se_puede_borrar_y_los_demas_no(self):
        d = Directorio.objects.create(email='ana@h.com', departamento='Recepción')
        self.client.post(reverse('catalogo_borrar', args=['directorio', d.pk]))
        self.assertFalse(Directorio.objects.exists())
        h = Hotel.objects.create(nombre='X')
        self.assertEqual(self.client.post(reverse('catalogo_borrar', args=['ubicaciones', h.pk])).status_code, 404)
        self.assertTrue(Hotel.objects.filter(pk=h.pk).exists())

    def test_catalogo_desconocido(self):
        self.assertEqual(self.client.get(reverse('catalogo', args=['nada'])).status_code, 404)

    def test_pantalla_muestra_estado_del_sistema(self):
        r = self.client.get(reverse('configuracion'))
        self.assertContains(r, 'Roles y permisos')
        self.assertFalse(r.context['sistema']['ia_configurada'])
