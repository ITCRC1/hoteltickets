"""
Pruebas de la Etapa 2: roles verificados en el servidor, login con correo, sesión expirada,
invitación por link, administración de usuarios y auditoría.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tickets.models import Categoria, Hotel, Ticket

from . import invitaciones, roles
from .models import Auditoria
from .views import COOKIE_SESION

CLAVE = 'clave-segura-123'


def crear(email, rol=None, **extra):
    u = User.objects.create_user(username=email, email=email, password=CLAVE, **extra)
    if rol:
        roles.asignar_rol(u, rol)
    return u


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', NOTIFICATION_EMAILS=[])
class Base(TestCase):
    def setUp(self):
        self.admin = crear('admin@x.com', roles.ADMIN)
        self.it = crear('it@x.com', roles.IT)
        self.lector = crear('lector@x.com', roles.LECTURA)
        self.sin_rol = crear('nadie@x.com')
        self.hotel = Hotel.objects.create(nombre='Hotel Prueba')
        self.cat = Categoria.objects.create(nombre='IT / Sistemas')
        self.ticket = Ticket.objects.create(titulo='PC no enciende', descripcion='x', hotel=self.hotel,
                                            categoria=self.cat, solicitante_nombre='Ana', solicitante_email='ana@h.com')

    def entrar(self, user):
        self.client.force_login(user)


class PermisosTickets(Base):
    def test_anonimo_va_al_login(self):
        r = self.client.get(reverse('ticket_lista'))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('login'), r['Location'])

    def test_sin_rol_no_entra(self):
        self.entrar(self.sin_rol)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 403)

    def test_los_tres_roles_consultan(self):
        for u in (self.admin, self.it, self.lector):
            self.entrar(u)
            for nombre, args in (('dashboard', []), ('ticket_lista', []), ('ticket_detalle', [self.ticket.pk])):
                self.assertEqual(self.client.get(reverse(nombre, args=args)).status_code, 200, (u, nombre))

    def test_solo_lectura_no_modifica_aunque_mande_el_post(self):
        self.entrar(self.lector)
        r = self.client.post(reverse('ticket_detalle', args=[self.ticket.pk]),
                             {'accion': 'gestion', 'estado': 'cerrado', 'categoria': self.cat.pk})
        self.assertEqual(r.status_code, 403)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, 'abierto')
        r = self.client.post(reverse('ticket_detalle', args=[self.ticket.pk]), {'accion': 'comentar', 'contenido': 'hola'})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(self.ticket.comentarios.exists())

    def test_solo_lectura_no_ve_formularios(self):
        self.entrar(self.lector)
        r = self.client.get(reverse('ticket_detalle', args=[self.ticket.pk]))
        self.assertNotContains(r, 'name="accion" value="gestion"')
        self.assertContains(r, 'solo lectura')

    def test_it_support_modifica(self):
        self.entrar(self.it)
        r = self.client.post(reverse('ticket_detalle', args=[self.ticket.pk]),
                             {'accion': 'gestion', 'estado': 'en_progreso', 'categoria': self.cat.pk,
                              'asignado_a': self.it.pk})
        self.assertEqual(r.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.estado, self.ticket.asignado_a), ('en_progreso', self.it))

    def test_asignar_solo_a_quien_atiende(self):
        from tickets.forms import TicketGestionForm
        opciones = set(TicketGestionForm(instance=self.ticket).fields['asignado_a'].queryset)
        self.assertEqual(opciones, {self.admin, self.it})

    def test_formulario_publico_sigue_abierto(self):
        self.assertEqual(self.client.get(reverse('ticket_publico')).status_code, 200)


class PermisosAdministracion(Base):
    def test_solo_admin_ve_usuarios_y_auditoria(self):
        for u, esperado in ((self.admin, 200), (self.it, 403), (self.lector, 403)):
            self.entrar(u)
            self.assertEqual(self.client.get(reverse('usuarios')).status_code, esperado, u)
            self.assertEqual(self.client.get(reverse('auditoria')).status_code, esperado, u)

    def test_it_no_puede_crear_usuarios_por_post(self):
        self.entrar(self.it)
        r = self.client.post(reverse('usuarios'), {'email': 'n@x.com', 'nombre': 'N', 'rol': roles.ADMIN})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(User.objects.filter(email='n@x.com').exists())


class Login(Base):
    def test_entra_con_correo_sin_importar_mayusculas(self):
        r = self.client.post(reverse('login'), {'username': 'IT@X.COM', 'password': CLAVE})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.cookies[COOKIE_SESION].value, '1')

    def test_entra_con_usuario(self):
        u = User.objects.create_user(username='soporte', email='otro@x.com', password=CLAVE)
        roles.asignar_rol(u, roles.IT)
        self.assertEqual(self.client.post(reverse('login'), {'username': 'soporte', 'password': CLAVE}).status_code, 302)

    def test_clave_incorrecta_y_auditoria(self):
        r = self.client.post(reverse('login'), {'username': 'it@x.com', 'password': 'mala'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'incorrectos')
        self.assertTrue(Auditoria.objects.filter(accion='INGRESO_FALLIDO').exists())

    def test_usuario_desactivado_no_entra(self):
        self.it.is_active = False
        self.it.save()
        self.assertEqual(self.client.post(reverse('login'), {'username': 'it@x.com', 'password': CLAVE}).status_code, 200)

    def test_aviso_de_sesion_expirada(self):
        self.client.cookies[COOKIE_SESION] = '1'  # tenía sesión en esta computadora…
        r = self.client.get(reverse('ticket_lista'), follow=True)  # …y ya no
        self.assertContains(r, 'Tu sesión expiró')

    def test_primera_visita_sin_aviso(self):
        r = self.client.get(reverse('ticket_lista'), follow=True)
        self.assertNotContains(r, 'Tu sesión expiró')

    def test_sesion_de_30_minutos(self):
        from django.conf import settings
        self.assertEqual(settings.SESSION_COOKIE_AGE, 30 * 60)


class Invitacion(Base):
    def crear_por_pantalla(self, **datos):
        self.entrar(self.admin)
        datos = {'email': 'Nuevo@X.com', 'nombre': 'Nuevo Técnico', 'rol': roles.IT, 'departamento': 'Recepción', **datos}
        r = self.client.post(reverse('usuarios'), datos, follow=True)
        self.client.logout()
        return r

    def token_de(self, respuesta):
        url = respuesta.context['link']['url']
        return url.rstrip('/').rsplit('/', 1)[-1]

    def test_crear_muestra_link_una_vez(self):
        r = self.crear_por_pantalla()
        u = User.objects.get(email='nuevo@x.com')
        self.assertFalse(u.has_usable_password())
        self.assertEqual((roles.rol(u), u.perfil.departamento), (roles.IT, 'Recepción'))
        self.assertIn('/invitacion/', r.context['link']['url'])
        self.entrar(self.admin)
        self.assertIsNone(self.client.get(reverse('usuarios')).context['link'])  # no se vuelve a mostrar
        token = self.token_de(r)
        self.assertNotEqual(u.perfil.invite_hash, token)  # en la base solo la huella
        self.assertEqual(u.perfil.invite_hash, invitaciones.huella(token))

    def test_flujo_completo_define_clave_y_entra(self):
        token = self.token_de(self.crear_por_pantalla())
        url = reverse('invitacion', args=[token])
        self.assertContains(self.client.get(url), 'nuevo@x.com')
        r = self.client.post(url, {'password1': 'MiClaveNueva2026', 'password2': 'MiClaveNueva2026'})
        self.assertRedirects(r, reverse('dashboard'))
        u = User.objects.get(email='nuevo@x.com')
        self.assertTrue(u.check_password('MiClaveNueva2026'))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        # un solo uso
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertTrue(Auditoria.objects.filter(accion='INVITACION_ACEPTADA', objeto_id=str(u.pk)).exists())
        # y desde ahí entra con su correo
        self.assertEqual(self.client.post(reverse('login'), {'username': 'nuevo@x.com', 'password': 'MiClaveNueva2026'}).status_code, 302)

    def test_reglas_de_clave(self):
        token = self.token_de(self.crear_por_pantalla())
        url = reverse('invitacion', args=[token])
        for p1, p2, error in (('corta1', 'corta1', '10 caracteres'),
                              ('soloLetrasLargas', 'soloLetrasLargas', 'letras y números'),
                              ('ClaveBuena123', 'ClaveBuena124', 'no coinciden')):
            self.assertContains(self.client.post(url, {'password1': p1, 'password2': p2}), error)
        self.assertFalse(User.objects.get(email='nuevo@x.com').has_usable_password())

    def test_link_vencido(self):
        token = self.token_de(self.crear_por_pantalla())
        perfil = User.objects.get(email='nuevo@x.com').perfil
        perfil.invite_exp = timezone.now() - timedelta(minutes=1)
        perfil.save()
        self.assertEqual(self.client.get(reverse('invitacion', args=[token])).status_code, 400)

    def test_link_nuevo_anula_el_anterior_y_sirve_para_olvido_de_clave(self):
        viejo = self.token_de(self.crear_por_pantalla())
        u = User.objects.get(email='nuevo@x.com')
        self.entrar(self.admin)
        r = self.client.post(reverse('usuario_invitar', args=[u.pk]), follow=True)
        nuevo = self.token_de(r)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('invitacion', args=[viejo])).status_code, 400)
        self.assertEqual(self.client.get(reverse('invitacion', args=[nuevo])).status_code, 200)

    def test_correo_duplicado(self):
        r = self.crear_por_pantalla(email='IT@x.com')
        self.assertContains(r, 'Ya existe un usuario con ese correo')

    def test_no_envia_correos(self):
        self.crear_por_pantalla()
        self.assertEqual(len(mail.outbox), 0)  # el admin decide por dónde manda el link


class EdicionUsuarios(Base):
    def editar(self, user, **datos):
        self.entrar(self.admin)
        base = {'nombre': user.get_full_name() or user.username, 'rol': roles.rol_asignado(user) or roles.LECTURA,
                'departamento': '', 'activo': 'on'}
        base.update(datos)
        datos = {f'u{user.pk}-{k}': v for k, v in base.items() if v is not None}
        return self.client.post(reverse('usuario_editar', args=[user.pk]), datos, follow=True)

    def test_cambiar_rol_queda_auditado_con_antes_y_despues(self):
        self.editar(self.lector, rol=roles.IT)
        self.assertEqual(roles.rol(User.objects.get(pk=self.lector.pk)), roles.IT)
        a = Auditoria.objects.get(accion='USUARIO_EDITADO')
        self.assertEqual(a.cambios['rol'], [roles.LECTURA, roles.IT])

    def test_desactivar(self):
        self.editar(self.it, activo=None)
        self.assertFalse(User.objects.get(pk=self.it.pk).is_active)

    def test_admin_no_se_quita_su_propio_acceso(self):
        r = self.editar(self.admin, rol=roles.LECTURA)
        self.assertContains(r, 'No puedes quitarte')
        self.assertEqual(roles.rol(User.objects.get(pk=self.admin.pk)), roles.ADMIN)

    def test_un_admin_puede_bajar_a_otro_admin(self):
        otro = crear('admin2@x.com', roles.ADMIN)
        self.editar(otro, rol=roles.IT)  # quien edita (self.admin) sigue siendo Administrador
        self.assertEqual(roles.rol(User.objects.get(pk=otro.pk)), roles.IT)

    def test_sin_cambios_no_audita(self):
        self.editar(self.it)
        self.assertFalse(Auditoria.objects.filter(accion='USUARIO_EDITADO').exists())

    def test_rol_admin_da_acceso_al_admin_tecnico(self):
        self.editar(self.it, rol=roles.ADMIN)
        u = User.objects.get(pk=self.it.pk)
        self.assertTrue(u.is_staff and u.is_superuser)
        self.editar(u, rol=roles.LECTURA)
        u = User.objects.get(pk=self.it.pk)
        self.assertFalse(u.is_staff or u.is_superuser)


class Ubicaciones(TestCase):
    def test_tipo_por_defecto_hotel(self):
        self.assertEqual(Hotel.objects.create(nombre='Nuevo').tipo, 'hotel')
