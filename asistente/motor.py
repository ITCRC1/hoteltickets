"""
Motor del asistente: un turno de conversación con Claude (API de Anthropic) y su ciclo de herramientas.

- Modelo: claude-opus-5-5 con razonamiento adaptativo y esfuerzo `medium` (explícito).
- Respaldo ante rechazos activado (fallbacks "default"): si el modelo declina por políticas de seguridad,
  la API reintenta con otro modelo dentro de la misma llamada.
- Caché: herramientas + instrucciones fijas van primero y se cachean; la fecha, el usuario y su rol van en un
  bloque aparte después del punto de caché, y la conversación se cachea con el cache_control de nivel superior.
- El historial es de solo anexar: los bloques de cada respuesta se guardan y se reenvían sin modificar.
- La clave vive en la variable ANTHROPIC_API_KEY de Railway (nunca en el código ni en la base de datos).
"""
import logging
import os

from django.db import transaction
from django.utils import timezone

from core import roles
from core.models import Parametro

from . import herramientas
from .models import Mensaje

logger = logging.getLogger(__name__)

MODELO = 'claude-opus-5-5'
ESFUERZO = 'medium'
MAX_TOKENS = 16000
MAX_VUELTAS = 8          # llamadas al modelo por mensaje del usuario (ciclo de herramientas)
BETAS = ['server-side-fallback-2026-07-01']

INSTRUCCIONES = """Eres el asistente del departamento de Tecnologías de Información de The Costa Rica Collection \
(hoteles Amarena Beach, Corcovado Wilderness Lodge, Ojochal Gardens y Oxygen Jungle Villas, y oficinas externas). \
Respondes en español, de forma clara y breve, a personas de TI y de administración.

Puedes ayudar con dos cosas:
1. Conocimiento general: informática, redes, servidores, sistemas operativos, seguridad, programación, bases de datos, \
redacción de correos y documentos, análisis de problemas y recomendaciones.
2. Datos reales de la plataforma, usando las herramientas: tickets, tareas, inventario, presupuesto, gastos, \
suscripciones y reportes en Excel. Cuando la pregunta sea sobre datos de la plataforma, consulta siempre con una \
herramienta; nunca inventes cifras ni registros. Si una herramienta no devuelve datos, dilo.

Reglas para modificar información:
- Nunca digas que algo quedó guardado. Las herramientas "proponer_*" solo crean una propuesta; el usuario la confirma \
con un botón en pantalla. Después de proponer, explica en una línea qué se va a hacer y pide que confirme abajo.
- Si una herramienta responde que el rol del usuario no lo permite, explícalo; no intentes otra forma de hacerlo.
- Para registrar un gasto necesitas fecha, concepto, categoría, monto y moneda; si falta algo, pregúntalo.

Formato: usa listas cortas y negritas cuando ayuden. Cuando una herramienta devuelva un "url" o "url_descarga", \
inclúyelo como enlace Markdown, por ejemplo [Ticket #12](/tickets/12/). Montos con separador de miles y la moneda \
($ para USD, ₡ para CRC)."""


class AsistenteNoDisponible(Exception):
    pass


class ErrorIA(Exception):
    """Falla al hablar con la API (ya registrada en la auditoría); el mensaje es legible para el usuario."""


def clave_configurada():
    return bool(os.environ.get('ANTHROPIC_API_KEY'))


def habilitado():
    return clave_configurada() and Parametro.obtener('ia_habilitada', 'si') == 'si'


def acciones_habilitadas():
    return Parametro.obtener('ia_acciones', 'si') == 'si'


def _cliente():
    import anthropic
    return anthropic.Anthropic(max_retries=2, timeout=110.0)


def _sistema(user):
    hoy = timezone.localdate()
    contexto = (f'Fecha de hoy: {hoy.isoformat()} (zona America/Costa_Rica). Usuario: '
                f'{user.get_full_name() or "sin nombre"}. Rol: {roles.rol(user)}.')
    return [
        {'type': 'text', 'text': INSTRUCCIONES, 'cache_control': {'type': 'ephemeral'}},
        {'type': 'text', 'text': contexto},
    ]


def _a_dict(bloque):
    """Bloque de la respuesta → dict serializable, sin alterar su contenido."""
    if isinstance(bloque, dict):
        return bloque
    return bloque.model_dump(mode='json', exclude_none=True, by_alias=True)


def _para_reenviar(contenido):
    """Regla de reenvío tras un respaldo a mitad de respuesta: antes del ÚLTIMO bloque `fallback` se omiten
    thinking / redacted_thinking / tool_use; el bloque `fallback` se conserva en su lugar. Sin respaldo, igual."""
    posiciones = [i for i, b in enumerate(contenido) if b.get('type') == 'fallback']
    if not posiciones:
        return contenido
    corte = posiciones[-1]
    return [b for i, b in enumerate(contenido)
            if i >= corte or b.get('type') not in ('thinking', 'redacted_thinking', 'tool_use')]


def historial(conversacion):
    return [{'role': m.rol, 'content': _para_reenviar(m.contenido) if m.rol == 'assistant' else m.contenido}
            for m in conversacion.mensajes.all()]


def _texto(contenido):
    return '\n\n'.join(b.get('text', '') for b in contenido if b.get('type') == 'text').strip()


def responder(conversacion, user, texto_usuario, cliente=None):
    """Agrega el mensaje del usuario, conversa con Claude (usando herramientas si hace falta) y guarda todo.

    Devuelve el texto final. Lanza AsistenteNoDisponible si no hay clave o está apagado; los errores de la API
    se registran y se devuelven como mensaje legible.
    """
    if not habilitado():
        raise AsistenteNoDisponible('El asistente no está configurado o está desactivado.')
    import anthropic

    cliente = cliente or _cliente()
    Mensaje.objects.create(conversacion=conversacion, rol='user', contenido=[{'type': 'text', 'text': texto_usuario}],
                           texto=texto_usuario)
    if conversacion.titulo == 'Nueva conversación':
        conversacion.titulo = texto_usuario.strip().split('\n')[0][:80] or conversacion.titulo
    conversacion.save()

    herramientas_api = herramientas.definiciones(acciones_habilitadas())
    final = ''
    for _ in range(MAX_VUELTAS):
        try:
            respuesta = cliente.beta.messages.create(
                model=MODELO, max_tokens=MAX_TOKENS, betas=BETAS, fallbacks='default',
                thinking={'type': 'adaptive'}, output_config={'effort': ESFUERZO},
                cache_control={'type': 'ephemeral'},
                system=_sistema(user), tools=herramientas_api, messages=historial(conversacion),
            )
        except anthropic.RateLimitError:
            return _error(conversacion, user, 'El servicio de IA está saturado en este momento. Intenta de nuevo en un minuto.')
        except anthropic.AuthenticationError:
            return _error(conversacion, user, 'La clave de la API de Anthropic no es válida. Avisa al Administrador.')
        except anthropic.APIStatusError as e:
            return _error(conversacion, user, f'El servicio de IA respondió con un error ({e.status_code}).', detalle=str(e.message))
        except anthropic.APIConnectionError:
            return _error(conversacion, user, 'No se pudo conectar con el servicio de IA. Intenta de nuevo.')

        contenido = [_a_dict(b) for b in respuesta.content]
        uso = respuesta.usage
        with transaction.atomic():
            Mensaje.objects.create(
                conversacion=conversacion, rol='assistant', contenido=contenido, texto=_texto(contenido),
                visible=bool(_texto(contenido)), modelo=respuesta.model,
                tokens_entrada=(uso.input_tokens or 0) + (getattr(uso, 'cache_creation_input_tokens', 0) or 0),
                tokens_salida=uso.output_tokens or 0, tokens_cache=getattr(uso, 'cache_read_input_tokens', 0) or 0)

        if respuesta.stop_reason == 'refusal':
            final = _texto(contenido) or 'No puedo ayudar con esa solicitud.'
            break
        if respuesta.stop_reason == 'pause_turn':
            continue
        if respuesta.stop_reason != 'tool_use':
            final = _texto(contenido)
            if respuesta.stop_reason == 'max_tokens':
                final += '\n\n_(La respuesta se cortó por su largo. Pide que continúe.)_'
            break

        resultados = []
        for bloque in contenido:
            if bloque.get('type') != 'tool_use':
                continue
            salida, es_error = herramientas.ejecutar(bloque['name'], bloque.get('input') or {}, user, conversacion)
            resultados.append({'type': 'tool_result', 'tool_use_id': bloque['id'], 'content': salida,
                               **({'is_error': True} if es_error else {})})
        # Todos los resultados en un solo mensaje (así el modelo sigue usando herramientas en paralelo).
        Mensaje.objects.create(conversacion=conversacion, rol='user', contenido=resultados, visible=False)
    else:
        final = final or 'Me detuve porque la consulta requería demasiados pasos. Intenta con una pregunta más concreta.'

    conversacion.save()
    return final


def _error(conversacion, user, mensaje, detalle=''):
    from core.auditoria import auditar
    logger.error('Asistente IA: %s %s', mensaje, detalle)
    auditar(None, 'ERROR_IA', 'asistente', objeto=conversacion, usuario=user, detalle=f'{mensaje} {detalle}'.strip()[:500])
    raise ErrorIA(mensaje)
