"""
Pruebas de la Etapa 11 (asistente IA). Usan un cliente simulado: no se llama a la API real ni se gasta nada.
Cubren: ciclo de herramientas, parámetros de la petición, permisos del usuario, propuestas con confirmación,
reglas de reenvío del historial, errores de la API, render seguro y configuración.
"""
import json
import os
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core import roles
from core.models import Auditoria, Parametro
from tareas.models import Tarea
from tickets.models import Categoria, Hotel, Ticket

from . import herramientas, motor
from .models import AccionPendiente, Conversacion, Mensaje
from .templatetags.asistente import markdown_seguro

CON_CLAVE = mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-prueba'})


class Bloque(SimpleNamespace):
    def model_dump(self, **kwargs):
        return {k: v for k, v in vars(self).items() if v is not None}


def texto(t):
    return Bloque(type='text', text=t)


def herramienta(id_, nombre, entrada):
    return Bloque(type='tool_use', id=id_, name=nombre, input=entrada)


def respuesta(bloques, stop='end_turn'):
    return SimpleNamespace(content=bloques, stop_reason=stop, model=motor.MODELO,
                           usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_creation_input_tokens=0,
                                                 cache_read_input_tokens=50))


class ClienteFalso:
    """Devuelve las respuestas en orden y guarda cada petición para revisarla."""
    def __init__(self, *respuestas, error=None):
        self.respuestas, self.peticiones, self.error = list(respuestas), [], error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._crear))

    def _crear(self, **kwargs):
        self.peticiones.append(json.loads(json.dumps(kwargs, default=str)))
        if self.error:
            raise self.error
        return self.respuestas.pop(0)


def usuario(email, rol, **extra):
    u = User.objects.create_user(username=email, email=email, password='clave-segura-123', **extra)
    roles.asignar_rol(u, rol)
    return u


@CON_CLAVE
class Motor(TestCase):
    def setUp(self):
        self.it = usuario('it@x.com', roles.IT, first_name='Ana')
        self.lector = usuario('lector@x.com', roles.LECTURA)
        self.admin = usuario('admin@x.com', roles.ADMIN)
        hotel = Hotel.objects.create(nombre='Hotel Amarena Beach')
        cat = Categoria.objects.create(nombre='IT / Sistemas')
        self.ticket = Ticket.objects.create(titulo='Servidor caído', descripcion='x', hotel=hotel, categoria=cat,
                                            prioridad='urgente', solicitante_nombre='Beto', solicitante_email='b@h.com')
        self.conv = Conversacion.objects.create(usuario=self.it)

    def test_ciclo_con_herramienta_y_parametros_de_la_peticion(self):
        cliente = ClienteFalso(
            respuesta([texto('Reviso.'), herramienta('t1', 'consultar_tickets', {'estado': 'pendientes'})], 'tool_use'),
            respuesta([texto('Hay **1** ticket pendiente: [Ticket #1](/tickets/1/).')]))
        final = motor.responder(self.conv, self.it, '¿Cuántos tickets pendientes hay?', cliente=cliente)
        self.assertIn('**1** ticket pendiente', final)

        p1, p2 = cliente.peticiones
        self.assertEqual(p1['model'], 'claude-opus-5-5')
        self.assertEqual((p1['fallbacks'], p1['betas']), ('default', ['server-side-fallback-2026-07-01']))
        self.assertEqual(p1['thinking'], {'type': 'adaptive'})
        self.assertEqual(p1['output_config'], {'effort': 'medium'})
        self.assertEqual(p1['system'][0]['cache_control'], {'type': 'ephemeral'})  # instrucciones fijas cacheadas
        self.assertNotIn('it@x.com', json.dumps(p1['system']))  # no se envía el correo del usuario
        self.assertIn('IT Support', p1['system'][1]['text'])
        nombres = [t['name'] for t in p1['tools']]
        self.assertEqual(nombres, list(herramientas.HERRAMIENTAS))  # orden fijo (caché)

        # La segunda petición reenvía la respuesta con la herramienta y su resultado
        ultimo = p2['messages'][-1]
        self.assertEqual(ultimo['role'], 'user')
        resultado = json.loads(ultimo['content'][0]['content'])
        self.assertEqual((ultimo['content'][0]['tool_use_id'], resultado['total']), ('t1', 1))
        self.assertEqual(p2['messages'][-2]['content'][1]['type'], 'tool_use')

        visibles = list(self.conv.mensajes.filter(visible=True).values_list('rol', flat=True))
        self.assertEqual(visibles, ['user', 'assistant', 'assistant'])
        self.assertEqual(self.conv.mensajes.filter(rol='assistant').first().tokens_cache, 50)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.titulo, '¿Cuántos tickets pendientes hay?')

    def test_bloques_de_razonamiento_se_reenvian_sin_cambios(self):
        pensado = Bloque(type='thinking', thinking='', signature='firma-abc')
        cliente = ClienteFalso(respuesta([pensado, texto('Hola')]), respuesta([texto('Sigo aquí')]))
        motor.responder(self.conv, self.it, 'Hola', cliente=cliente)
        motor.responder(self.conv, self.it, '¿Sigues?', cliente=cliente)
        asistente = cliente.peticiones[1]['messages'][1]
        self.assertEqual(asistente['content'][0], {'type': 'thinking', 'thinking': '', 'signature': 'firma-abc'})

    def test_regla_de_reenvio_tras_respaldo(self):
        contenido = [{'type': 'thinking', 'thinking': '', 'signature': 'a'}, {'type': 'text', 'text': 'parcial'},
                     {'type': 'fallback', 'from': {'model': 'x'}, 'to': {'model': 'y'}},
                     {'type': 'thinking', 'thinking': '', 'signature': 'b'}, {'type': 'text', 'text': 'final'}]
        tipos = [b['type'] for b in motor._para_reenviar(contenido)]
        self.assertEqual(tipos, ['text', 'fallback', 'thinking', 'text'])
        sin = [{'type': 'thinking', 'signature': 's'}, {'type': 'text', 'text': 'x'}]
        self.assertEqual(motor._para_reenviar(sin), sin)

    def test_herramienta_desconocida_o_parametros_malos(self):
        salida, error = herramientas.ejecutar('borrar_todo', {}, self.it, self.conv)
        self.assertTrue(error)
        salida, error = herramientas.ejecutar('consultar_tickets', {'inventado': 1}, self.it, self.conv)
        self.assertTrue(error)

    def test_error_de_api_se_avisa_y_se_audita(self):
        import anthropic
        import httpx2
        req = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')
        err = anthropic.RateLimitError('limite', response=httpx2.Response(429, request=req), body=None)
        with self.assertRaises(motor.ErrorIA):
            motor.responder(self.conv, self.it, 'Hola', cliente=ClienteFalso(error=err))
        self.assertTrue(Auditoria.objects.filter(accion='ERROR_IA').exists())

    def test_limite_de_vueltas(self):
        vueltas = [respuesta([herramienta(f't{i}', 'consultar_tareas', {})], 'tool_use') for i in range(motor.MAX_VUELTAS)]
        final = motor.responder(self.conv, self.it, 'x', cliente=ClienteFalso(*vueltas))
        self.assertIn('demasiados pasos', final)

    def test_rechazo_del_modelo(self):
        final = motor.responder(self.conv, self.it, 'x', cliente=ClienteFalso(respuesta([], 'refusal')))
        self.assertEqual(final, 'No puedo ayudar con esa solicitud.')


@CON_CLAVE
class Permisos(TestCase):
    def setUp(self):
        self.it = usuario('it@x.com', roles.IT)
        self.lector = usuario('lector@x.com', roles.LECTURA)
        self.admin = usuario('admin@x.com', roles.ADMIN)

    def conv(self, u):
        return Conversacion.objects.create(usuario=u)

    def test_solo_lectura_no_puede_proponer(self):
        salida, error = herramientas.ejecutar('proponer_tarea', {'titulo': 'X'}, self.lector, self.conv(self.lector))
        self.assertIn('no permite', salida)
        self.assertFalse(AccionPendiente.objects.exists())

    def test_it_no_registra_gastos(self):
        salida, _ = herramientas.ejecutar('proponer_gasto', {'fecha': '2026-11-01', 'concepto': 'X', 'categoria': 'Hardware',
                                                             'monto': 10}, self.it, self.conv(self.it))
        self.assertIn('Solo el Administrador', salida)

    def test_propuesta_no_guarda_hasta_confirmar(self):
        c = self.conv(self.it)
        salida, error = herramientas.ejecutar('proponer_tarea', {'titulo': 'Revisar UPS', 'fecha_vencimiento': '2026-11-20',
                                                                 'prioridad': 'alta', 'asignarme': True}, self.it, c)
        self.assertFalse(error)
        self.assertFalse(Tarea.objects.exists())
        accion = AccionPendiente.objects.get()
        self.client.force_login(self.it)
        self.client.post(reverse('asistente_accion', args=[accion.pk, 'confirmar']))
        t = Tarea.objects.get()
        self.assertEqual((t.titulo, t.prioridad, t.responsable, str(t.fecha_vencimiento)), ('Revisar UPS', 'alta', self.it, '2026-11-20'))
        accion.refresh_from_db()
        self.assertEqual(accion.estado, 'confirmada')
        self.assertTrue(Auditoria.objects.filter(modulo='tareas', detalle__contains='Vía asistente IA').exists())
        # el modelo se entera en el próximo turno
        self.assertIn('CONFIRMÓ', c.mensajes.last().texto)
        # no se puede confirmar dos veces
        self.assertEqual(self.client.post(reverse('asistente_accion', args=[accion.pk, 'confirmar'])).status_code, 404)

    def test_rechazar_no_guarda(self):
        c = self.conv(self.it)
        herramientas.ejecutar('proponer_tarea', {'titulo': 'X'}, self.it, c)
        accion = AccionPendiente.objects.get()
        self.client.force_login(self.it)
        self.client.post(reverse('asistente_accion', args=[accion.pk, 'rechazar']))
        self.assertFalse(Tarea.objects.exists())

    def test_otro_usuario_no_confirma(self):
        c = self.conv(self.it)
        herramientas.ejecutar('proponer_tarea', {'titulo': 'X'}, self.it, c)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('asistente_accion', args=[AccionPendiente.objects.get().pk, 'confirmar'])).status_code, 404)
        self.assertFalse(Tarea.objects.exists())

    def test_permiso_se_revalida_al_confirmar(self):
        c = self.conv(self.it)
        herramientas.ejecutar('proponer_tarea', {'titulo': 'X'}, self.it, c)
        roles.asignar_rol(self.it, roles.LECTURA)  # le bajaron el rol antes de confirmar
        self.client.force_login(self.it)
        self.client.post(reverse('asistente_accion', args=[AccionPendiente.objects.get().pk, 'confirmar']))
        self.assertFalse(Tarea.objects.exists())
        self.assertEqual(AccionPendiente.objects.get().estado, 'error')

    def test_gasto_del_admin(self):
        from finanzas.models import Gasto
        c = self.conv(self.admin)
        salida, error = herramientas.ejecutar('proponer_gasto', {'fecha': '2026-11-05', 'concepto': 'Disco SSD', 'categoria': 'hardware',
                                                                 'monto': 120.5, 'moneda': 'USD'}, self.admin, c)
        self.assertFalse(error, salida)
        self.client.force_login(self.admin)
        self.client.post(reverse('asistente_accion', args=[AccionPendiente.objects.get().pk, 'confirmar']))
        self.assertEqual(str(Gasto.objects.get().monto), '120.50')

    def test_conversaciones_privadas(self):
        c = self.conv(self.it)
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(reverse('asistente_conversacion', args=[c.pk])).status_code, 404)


class Pantallas(TestCase):
    def setUp(self):
        self.admin = usuario('admin@x.com', roles.ADMIN)
        self.it = usuario('it@x.com', roles.IT)

    def test_sin_clave_se_avisa_y_no_se_llama(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ANTHROPIC_API_KEY', None)
            self.client.force_login(self.it)
            r = self.client.get(reverse('asistente'))
            self.assertContains(r, 'falta la clave')
            r = self.client.post(reverse('asistente_enviar'), {'texto': 'hola'}, follow=True)
            self.assertContains(r, 'no está configurado')
            self.assertFalse(Mensaje.objects.exists())

    @CON_CLAVE
    def test_admin_desactiva(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('configuracion_ia'), {'ia_acciones': 'on'})  # sin ia_habilitada → apagado
        self.assertFalse(motor.habilitado())
        self.assertTrue(Auditoria.objects.filter(modulo='asistente', accion='EDITADO').exists())
        self.client.post(reverse('configuracion_ia'), {'ia_habilitada': 'on'})
        self.assertTrue(motor.habilitado())
        self.assertFalse(motor.acciones_habilitadas())
        nombres = [h['name'] for h in herramientas.definiciones(motor.acciones_habilitadas())]
        self.assertNotIn('proponer_tarea', nombres)

    def test_configuracion_solo_admin(self):
        self.client.force_login(self.it)
        self.assertEqual(self.client.get(reverse('configuracion_ia')).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('configuracion_ia')).status_code, 200)

    @CON_CLAVE
    def test_enviar_desde_la_pantalla(self):
        self.client.force_login(self.it)
        with mock.patch.object(motor, '_cliente', return_value=ClienteFalso(respuesta([texto('¡Hola!')]))):
            r = self.client.post(reverse('asistente_enviar'), {'texto': 'Hola'}, follow=True)
        self.assertContains(r, '¡Hola!')


class RenderSeguro(TestCase):
    def test_escapa_html_y_solo_enlaces_internos(self):
        html = markdown_seguro('<script>alert(1)</script> **ok** [x](/tickets/1/) [malo](https://evil.com) '
                               '[js](javascript:alert(1)) [doble](//evil.com)\n- uno\n- dos')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('<strong>ok</strong>', html)
        self.assertIn('<a href="/tickets/1/">x</a>', html)
        self.assertNotIn('href="https://evil.com"', html)
        self.assertNotIn('href="javascript', html)
        self.assertNotIn('href="//evil.com"', html)
        self.assertIn('<ul class="mb-2"><li>uno</li><li>dos</li></ul>', html)
