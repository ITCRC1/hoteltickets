"""
Herramientas que Claude puede usar dentro de la app.

Reglas:
  - Cada herramienta corre con el usuario que conversa: nunca con más permisos que su rol.
  - Las de consulta devuelven datos reales (tope de filas para no inflar el contexto).
  - Las de acción NO modifican nada: crean una AccionPendiente que el usuario confirma o rechaza en pantalla;
    al confirmar se vuelven a validar los permisos y los datos (ver `ejecutar_accion`).
"""
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from core import roles

LIMITE = 25


def _json(datos):
    return json.dumps(datos, ensure_ascii=False, default=str)


def _nombre(u):
    return (u.get_full_name() or u.username) if u else None


def _fecha(valor):
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


# ------------------------------------------------------------------ consultas

def consultar_tickets(user, estado='pendientes', prioridad='', ubicacion='', texto='', solo_mios=False):
    from tickets.models import Ticket
    qs = Ticket.objects.select_related('hotel', 'asignado_a')
    if estado == 'pendientes':
        qs = qs.filter(estado__in=Ticket.ESTADOS_ABIERTOS)
    elif estado and estado != 'todos':
        qs = qs.filter(estado=estado)
    if prioridad:
        qs = qs.filter(prioridad=prioridad)
    if ubicacion:
        qs = qs.filter(hotel__nombre__icontains=ubicacion)
    if texto:
        qs = qs.filter(Q(titulo__icontains=texto) | Q(descripcion__icontains=texto) | Q(solicitante_nombre__icontains=texto))
    if solo_mios:
        qs = qs.filter(asignado_a=user)
    por_estado = dict(qs.values_list('estado').annotate(n=Count('id')))
    return _json({
        'total': qs.count(), 'por_estado': por_estado,
        'tickets': [{'numero': t.pk, 'titulo': t.titulo, 'ubicacion': str(t.hotel), 'estado': t.get_estado_display(),
                     'prioridad': t.get_prioridad_display(), 'responsable': _nombre(t.asignado_a),
                     'solicitante': t.solicitante_nombre, 'creado': t.creado_en.date().isoformat(),
                     'url': reverse('ticket_detalle', args=[t.pk])}
                    for t in qs.order_by('-creado_en')[:LIMITE]],
        'nota': f'Se muestran como máximo {LIMITE}.' if qs.count() > LIMITE else '',
    })


def consultar_tareas(user, periodo='semana', estado='abiertas', solo_mias=False):
    from tareas.models import Tarea
    hoy = timezone.localdate()
    qs = Tarea.objects.select_related('responsable')
    rangos = {'hoy': (hoy, hoy), 'manana': (hoy + timedelta(days=1), hoy + timedelta(days=1)),
              'semana': (hoy - timedelta(days=hoy.weekday()), hoy - timedelta(days=hoy.weekday()) + timedelta(days=6)),
              'proximos_7': (hoy, hoy + timedelta(days=7)), 'mes': (hoy.replace(day=1), (hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))}
    if periodo == 'vencidas':
        qs = qs.filter(fecha_vencimiento__lt=hoy).exclude(estado='completada')
    elif periodo in rangos:
        qs = qs.filter(fecha_vencimiento__range=rangos[periodo])
    if estado == 'abiertas':
        qs = qs.exclude(estado='completada')
    elif estado and estado != 'todas':
        qs = qs.filter(estado=estado)
    if solo_mias:
        qs = qs.filter(responsable=user)
    return _json({
        'periodo': periodo, 'total': qs.count(),
        'tareas': [{'titulo': t.titulo, 'vence': t.fecha_vencimiento, 'estado': t.get_estado_display(),
                    'prioridad': t.get_prioridad_display(), 'responsable': _nombre(t.responsable),
                    'url': reverse('tarea_editar', args=[t.pk])} for t in qs[:LIMITE]],
    })


def consultar_inventario(user, categoria='', ubicacion='', departamento='', texto='', agrupar_por=''):
    from inventario.models import Activo
    qs = Activo.objects.select_related('categoria', 'estado', 'ubicacion')
    if categoria:
        qs = qs.filter(categoria__nombre__icontains=categoria)
    if ubicacion:
        qs = qs.filter(ubicacion__nombre__icontains=ubicacion)
    if departamento:
        qs = qs.filter(departamento__icontains=departamento)
    if texto:
        qs = qs.filter(Q(codigo__icontains=texto) | Q(nombre__icontains=texto) | Q(marca__icontains=texto) |
                       Q(modelo__icontains=texto) | Q(numero_serie__icontains=texto) | Q(responsable__icontains=texto))
    salida = {'total': qs.count()}
    campos = {'categoria': 'categoria__nombre', 'ubicacion': 'ubicacion__nombre', 'estado': 'estado__nombre',
              'departamento': 'departamento'}
    if agrupar_por in campos:
        salida['agrupado'] = {k or '(sin dato)': n for k, n in qs.values_list(campos[agrupar_por]).annotate(n=Count('id')).order_by('-n')}
    salida['equipos'] = [{'codigo': a.codigo, 'nombre': a.nombre, 'categoria': str(a.categoria), 'marca': a.marca,
                          'modelo': a.modelo, 'serie': a.numero_serie, 'ubicacion': str(a.ubicacion),
                          'departamento': a.departamento, 'responsable': a.responsable, 'estado': str(a.estado),
                          'garantia_hasta': a.garantia_hasta, 'url': reverse('activo_editar', args=[a.pk])}
                         for a in qs[:LIMITE]]
    return _json(salida)


def consultar_finanzas(user, anio=None, moneda='USD'):
    from finanzas.calculos import resumen_anual
    hoy = timezone.localdate()
    anio = int(anio) if str(anio or '').isdigit() else hoy.year
    moneda = 'CRC' if moneda == 'CRC' else 'USD'
    r = resumen_anual(anio, moneda, hoy)
    t = r['total']
    return _json({
        'anio': anio, 'moneda': moneda,
        'total': {k: t[k] for k in ('asignado', 'utilizado', 'pagado', 'pendiente', 'disponible', 'proyeccion', 'suscripciones')},
        'ejecucion_pct': round(t['ejecucion'], 1) if t['ejecucion'] is not None else None,
        'por_categoria': [{'categoria': str(c['categoria']), 'asignado': c['asignado'], 'utilizado': c['utilizado'],
                           'disponible': c['disponible'], 'proyeccion_cierre': c['proyeccion']} for c in r['categorias']],
        'gasto_por_mes': {m['mes']: m['monto'] for m in r['por_mes'] if m['monto']},
        'advertencia': (f"{len(r['sin_tipo'])} gastos y {len(r['presupuesto_sin_tipo'])} presupuestos no se incluyen "
                        f"porque falta el tipo de cambio de su mes") if r['sin_tipo'] or r['presupuesto_sin_tipo'] else '',
    })


def consultar_gastos(user, anio=None, mes=None, categoria='', proveedor=''):
    from finanzas.models import Gasto
    qs = Gasto.objects.select_related('categoria').exclude(estado='anulado')
    if str(anio or '').isdigit():
        qs = qs.filter(fecha__year=int(anio))
    if str(mes or '').isdigit():
        qs = qs.filter(fecha__month=int(mes))
    if categoria:
        qs = qs.filter(categoria__nombre__icontains=categoria)
    if proveedor:
        qs = qs.filter(proveedor__icontains=proveedor)
    total_usd, sin_tipo = Decimal('0'), 0
    for g in qs:
        v = g.monto_en('USD')
        if v is None:
            sin_tipo += 1
        else:
            total_usd += v
    return _json({'cantidad': qs.count(), 'total_usd': total_usd, 'sin_tipo_de_cambio': sin_tipo,
                  'gastos': [{'fecha': g.fecha, 'concepto': g.concepto, 'categoria': str(g.categoria),
                              'proveedor': g.proveedor, 'monto': g.monto, 'moneda': g.moneda, 'estado': g.get_estado_display()}
                             for g in qs[:LIMITE]]})


def consultar_suscripciones(user, dias=30, estado='activa'):
    from finanzas.models import Suscripcion
    hoy = timezone.localdate()
    qs = Suscripcion.objects.select_related('categoria')
    if estado:
        qs = qs.filter(estado=estado)
    if dias:
        qs = qs.filter(proxima_renovacion__lte=hoy + timedelta(days=int(dias)))
    return _json({'total': qs.count(),
                  'suscripciones': [{'servicio': s.nombre, 'proveedor': s.proveedor, 'costo': s.costo, 'moneda': s.moneda,
                                     'frecuencia': s.get_frecuencia_display(), 'proxima_renovacion': s.proxima_renovacion,
                                     'vencida': bool(s.proxima_renovacion and s.proxima_renovacion < hoy),
                                     'costo_anual': s.costo_anual} for s in qs[:LIMITE]]})


REPORTES = {'inventario': 'exportar_inventario', 'tickets': 'exportar_tickets', 'tareas': 'exportar_tareas',
            'gastos': 'exportar_gastos', 'suscripciones': 'exportar_suscripciones', 'presupuesto': 'exportar_presupuesto'}


def preparar_reporte(user, tipo, filtros=None):
    if tipo not in REPORTES:
        return _json({'error': f'Tipo de reporte desconocido. Opciones: {", ".join(REPORTES)}'})
    permitidos = {'estado', 'prioridad', 'q', 'categoria', 'ubicacion', 'hotel', 'anio', 'mes', 'moneda', 'vence',
                  'garantia', 'renovacion', 'proveedor', 'departamento'}
    limpios = {k: str(v) for k, v in (filtros or {}).items() if k in permitidos and v not in (None, '')}
    url = reverse(REPORTES[tipo]) + (f'?{urlencode(limpios)}' if limpios else '')
    return _json({'url_descarga': url, 'nota': 'Comparte este enlace con el usuario para que descargue el Excel.'})


# ------------------------------------------------------------------ acciones (solo propuestas)

def proponer_tarea(user, titulo, descripcion='', fecha_vencimiento='', prioridad='normal', asignarme=False, *, conversacion):
    if not roles.puede_editar(user):
        return _json({'error': 'El rol del usuario no permite crear tareas.'})
    if not (titulo or '').strip():
        return _json({'error': 'Falta el título.'})
    if prioridad not in ('baja', 'normal', 'alta', 'urgente'):
        prioridad = 'normal'
    vence = _fecha(fecha_vencimiento)
    datos = {'titulo': titulo.strip()[:200], 'descripcion': (descripcion or '').strip(),
             'fecha_vencimiento': vence.isoformat() if vence else '', 'prioridad': prioridad, 'asignarme': bool(asignarme)}
    resumen = (f'Crear tarea "{datos["titulo"]}" · prioridad {prioridad}'
               + (f' · vence {vence:%d/%m/%Y}' if vence else ' · sin fecha') + (' · asignada a ti' if asignarme else ''))
    return _proponer(conversacion, user, 'crear_tarea', datos, resumen)


def proponer_gasto(user, fecha, concepto, categoria, monto, moneda='USD', proveedor='', estado='pagado', *, conversacion):
    from finanzas.models import CategoriaGasto
    if not roles.es_admin(user):
        return _json({'error': 'Solo el Administrador registra gastos.'})
    f = _fecha(fecha)
    cat = CategoriaGasto.objects.filter(nombre__iexact=(categoria or '').strip(), activa=True).first()
    try:
        valor = Decimal(str(monto)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        valor = None
    errores = [m for c, m in ((f, 'fecha inválida (AAAA-MM-DD)'), (cat, 'categoría inexistente'),
                               (valor and valor > 0, 'monto inválido'), ((concepto or '').strip(), 'falta el concepto')) if not c]
    if errores:
        nombres = ', '.join(CategoriaGasto.objects.filter(activa=True).values_list('nombre', flat=True))
        return _json({'error': '; '.join(errores), 'categorias_validas': nombres})
    moneda = 'CRC' if moneda == 'CRC' else 'USD'
    estado = estado if estado in ('pendiente', 'pagado') else 'pagado'
    datos = {'fecha': f.isoformat(), 'concepto': concepto.strip()[:200], 'categoria_id': cat.pk, 'monto': str(valor),
             'moneda': moneda, 'proveedor': (proveedor or '').strip()[:120], 'estado': estado}
    resumen = (f'Registrar gasto "{datos["concepto"]}" · {cat} · {"$" if moneda == "USD" else "₡"}{valor:,.2f} {moneda} · '
               f'{f:%d/%m/%Y} · {"pagado" if estado == "pagado" else "pendiente de pago"}'
               + (f' · {datos["proveedor"]}' if datos['proveedor'] else ''))
    return _proponer(conversacion, user, 'registrar_gasto', datos, resumen)


def proponer_actualizar_ticket(user, numero, estado='', prioridad='', asignarme=False, nota='', *, conversacion):
    from tickets.models import Ticket
    if not roles.puede_editar(user):
        return _json({'error': 'El rol del usuario no permite modificar tickets.'})
    t = Ticket.objects.filter(pk=numero).first()
    if t is None:
        return _json({'error': f'No existe el ticket #{numero}.'})
    datos = {'numero': t.pk}
    partes = []
    if estado in dict(Ticket.ESTADO_CHOICES) and estado != t.estado:
        datos['estado'] = estado
        partes.append(f'estado {t.get_estado_display()} → {dict(Ticket.ESTADO_CHOICES)[estado]}')
    if prioridad in dict(Ticket.PRIORIDAD_CHOICES) and prioridad != t.prioridad:
        datos['prioridad'] = prioridad
        partes.append(f'prioridad {t.get_prioridad_display()} → {dict(Ticket.PRIORIDAD_CHOICES)[prioridad]}')
    if asignarme and t.asignado_a_id != user.pk:
        datos['asignarme'] = True
        partes.append('asignártelo a ti')
    if (nota or '').strip():
        datos['nota'] = nota.strip()[:2000]
        partes.append('agregar una nota al historial')
    if not partes:
        return _json({'error': 'No hay cambios que proponer para ese ticket.'})
    return _proponer(conversacion, user, 'actualizar_ticket', datos, f'Ticket #{t.pk} "{t.titulo}": ' + '; '.join(partes))


def _proponer(conversacion, user, tipo, datos, resumen):
    from .models import AccionPendiente
    accion = AccionPendiente.objects.create(conversacion=conversacion, usuario=user, tipo=tipo, datos=datos, resumen=resumen)
    return _json({'estado': 'propuesta_creada', 'accion_id': accion.pk, 'resumen': resumen,
                  'nota': 'NO se ha guardado nada. El usuario debe pulsar Confirmar en pantalla.'})


def ejecutar_accion(accion, user, request=None):
    """Ejecuta una acción confirmada. Re-valida permisos y datos; devuelve (ok, mensaje)."""
    from core.auditoria import auditar
    if accion.usuario_id != user.pk:
        return False, 'Esta acción es de otro usuario.'
    d = accion.datos
    if accion.tipo == 'crear_tarea':
        from tareas.models import Tarea
        if not roles.puede_editar(user):
            return False, 'Tu rol ya no permite crear tareas.'
        t = Tarea.objects.create(titulo=d['titulo'], descripcion=d['descripcion'], prioridad=d['prioridad'],
                                 fecha_vencimiento=_fecha(d['fecha_vencimiento']), creado_por=user,
                                 responsable=user if d.get('asignarme') else None)
        auditar(request, 'CREADA', 'tareas', objeto=t, usuario=user, detalle=f'Vía asistente IA · {t.resumen_para_auditoria()}')
        return True, f'Tarea creada: {reverse("tarea_editar", args=[t.pk])}'
    if accion.tipo == 'registrar_gasto':
        from finanzas.models import CategoriaGasto, Gasto
        if not roles.es_admin(user):
            return False, 'Solo el Administrador registra gastos.'
        cat = CategoriaGasto.objects.filter(pk=d['categoria_id']).first()
        if cat is None:
            return False, 'La categoría ya no existe.'
        g = Gasto.objects.create(fecha=_fecha(d['fecha']), concepto=d['concepto'], categoria=cat, monto=Decimal(d['monto']),
                                 moneda=d['moneda'], proveedor=d['proveedor'], estado=d['estado'], creado_por=user)
        auditar(request, 'CREADO', 'gasto', objeto=g, usuario=user, detalle=f'Vía asistente IA · {g.resumen_para_auditoria()}')
        return True, f'Gasto registrado: {reverse("gasto_editar", args=[g.pk])}'
    if accion.tipo == 'actualizar_ticket':
        from tickets.models import RegistroAuditoria, Ticket
        if not roles.puede_editar(user):
            return False, 'Tu rol ya no permite modificar tickets.'
        t = Ticket.objects.filter(pk=d['numero']).first()
        if t is None:
            return False, 'El ticket ya no existe o está en la papelera.'
        if 'estado' in d and d['estado'] != t.estado:
            antes = t.get_estado_display()
            t.estado = d['estado']
            ahora = timezone.now()
            if t.estado == 'resuelto' and not t.resuelto_en:
                t.resuelto_en = ahora
            if t.estado == 'cerrado' and not t.cerrado_en:
                t.cerrado_en = ahora
            if t.estado not in ('resuelto', 'cerrado'):
                t.resuelto_en = t.cerrado_en = None
            t.save()
            RegistroAuditoria.registrar(ticket=t, accion='cambio_estado', usuario=user, anterior=antes,
                                        nuevo=t.get_estado_display(), detalle='Vía asistente IA')
            if t.estado == 'resuelto':
                from tickets import notifications
                notifications.notificar_resolucion(t)
        if 'prioridad' in d and d['prioridad'] != t.prioridad:
            antes = t.get_prioridad_display()
            t.prioridad = d['prioridad']
            t.save(update_fields=['prioridad', 'actualizado_en'])
            RegistroAuditoria.registrar(ticket=t, accion='cambio_prioridad', usuario=user, anterior=antes,
                                        nuevo=t.get_prioridad_display(), detalle='Vía asistente IA')
        if d.get('asignarme') and t.asignado_a_id != user.pk:
            antes = _nombre(t.asignado_a) or 'Sin asignar'
            t.asignado_a = user
            t.save(update_fields=['asignado_a', 'actualizado_en'])
            RegistroAuditoria.registrar(ticket=t, accion='asignar', usuario=user, anterior=antes, nuevo=_nombre(user),
                                        detalle='Vía asistente IA')
        if d.get('nota'):
            RegistroAuditoria.registrar(ticket=t, accion='nota', usuario=user, detalle=d['nota'])
        return True, f'Ticket #{t.pk} actualizado: {reverse("ticket_detalle", args=[t.pk])}'
    return False, 'Tipo de acción desconocido.'


# ------------------------------------------------------------------ definición para la API

def _obj(propiedades, requeridos=()):
    return {'type': 'object', 'properties': propiedades, 'required': list(requeridos), 'additionalProperties': False}


S = {'type': 'string'}
B = {'type': 'boolean'}

HERRAMIENTAS = {
    'consultar_tickets': (consultar_tickets, 'Consulta tickets de soporte (incidencias que reportan los hoteles). '
                          'Devuelve el total, el conteo por estado y hasta 25 tickets con su enlace.',
                          _obj({'estado': {'type': 'string', 'enum': ['pendientes', 'todos', 'abierto', 'en_progreso', 'en_espera', 'resuelto', 'cerrado'],
                                           'description': '"pendientes" = abierto + en progreso + en espera'},
                                'prioridad': {'type': 'string', 'enum': ['', 'baja', 'normal', 'alta', 'urgente']},
                                'ubicacion': {**S, 'description': 'Parte del nombre del hotel u oficina'},
                                'texto': {**S, 'description': 'Busca en título, descripción y solicitante'},
                                'solo_mios': {**B, 'description': 'Solo los asignados al usuario que pregunta'}})),
    'consultar_tareas': (consultar_tareas, 'Consulta las tareas del departamento de TI por período.',
                         _obj({'periodo': {'type': 'string', 'enum': ['hoy', 'manana', 'semana', 'proximos_7', 'mes', 'vencidas', 'todas'],
                                           'description': '"semana" = lunes a domingo de la semana actual'},
                               'estado': {'type': 'string', 'enum': ['abiertas', 'todas', 'pendiente', 'en_progreso', 'completada']},
                               'solo_mias': {**B, 'description': 'Solo las asignadas al usuario que pregunta'}})),
    'consultar_inventario': (consultar_inventario, 'Consulta el inventario de equipos (computadoras, impresoras, UPS, '
                             'cámaras, etc.). Permite filtrar y agrupar para contar.',
                             _obj({'categoria': S, 'ubicacion': S, 'departamento': S,
                                   'texto': {**S, 'description': 'Código, nombre, marca, modelo, serie o responsable'},
                                   'agrupar_por': {'type': 'string', 'enum': ['', 'categoria', 'ubicacion', 'estado', 'departamento']}})),
    'consultar_finanzas': (consultar_finanzas, 'Presupuesto anual de TI vs gasto real por categoría: asignado, utilizado, '
                           'disponible, proyección de cierre y gasto por mes.',
                           _obj({'anio': {'type': 'integer'}, 'moneda': {'type': 'string', 'enum': ['USD', 'CRC']}})),
    'consultar_gastos': (consultar_gastos, 'Lista gastos de TI (sin anulados) con filtros.',
                         _obj({'anio': {'type': 'integer'}, 'mes': {'type': 'integer', 'minimum': 1, 'maximum': 12},
                               'categoria': S, 'proveedor': S})),
    'consultar_suscripciones': (consultar_suscripciones, 'Suscripciones y servicios recurrentes que renuevan en los '
                                'próximos N días (incluye las vencidas).',
                                _obj({'dias': {'type': 'integer', 'minimum': 0, 'maximum': 366},
                                      'estado': {'type': 'string', 'enum': ['activa', 'pausada', 'cancelada', '']}})),
    'preparar_reporte': (preparar_reporte, 'Genera el enlace de descarga de un reporte en Excel con filtros.',
                         _obj({'tipo': {'type': 'string', 'enum': list(REPORTES)},
                               'filtros': {'type': 'object', 'description': 'Mismos filtros de la lista del módulo, '
                                           'p. ej. {"estado": "abiertos", "prioridad": "urgente"} o {"anio": 2026}',
                                           'additionalProperties': {'type': ['string', 'integer']}}}, ['tipo'])),
    'proponer_tarea': (proponer_tarea, 'PROPONE crear una tarea. No guarda nada: el usuario la confirma en pantalla.',
                       _obj({'titulo': S, 'descripcion': S,
                             'fecha_vencimiento': {**S, 'description': 'AAAA-MM-DD'},
                             'prioridad': {'type': 'string', 'enum': ['baja', 'normal', 'alta', 'urgente']},
                             'asignarme': {**B, 'description': 'Asignarla al usuario que pide'}}, ['titulo'])),
    'proponer_gasto': (proponer_gasto, 'PROPONE registrar un gasto de TI. No guarda nada: el usuario lo confirma en '
                       'pantalla. Solo para Administradores.',
                       _obj({'fecha': {**S, 'description': 'AAAA-MM-DD'}, 'concepto': S,
                             'categoria': {**S, 'description': 'Nombre exacto de la categoría (Hardware, Software, Licencias…)'},
                             'monto': {'type': 'number'}, 'moneda': {'type': 'string', 'enum': ['USD', 'CRC']},
                             'proveedor': S, 'estado': {'type': 'string', 'enum': ['pagado', 'pendiente']}},
                            ['fecha', 'concepto', 'categoria', 'monto'])),
    'proponer_actualizar_ticket': (proponer_actualizar_ticket, 'PROPONE cambiar el estado o la prioridad de un ticket, '
                                   'asignárselo al usuario o agregar una nota. No guarda nada hasta que el usuario confirme.',
                                   _obj({'numero': {'type': 'integer'},
                                         'estado': {'type': 'string', 'enum': ['', 'abierto', 'en_progreso', 'en_espera', 'resuelto', 'cerrado']},
                                         'prioridad': {'type': 'string', 'enum': ['', 'baja', 'normal', 'alta', 'urgente']},
                                         'asignarme': B, 'nota': S}, ['numero'])),
}
ACCIONES = {'proponer_tarea', 'proponer_gasto', 'proponer_actualizar_ticket'}


def definiciones(acciones_habilitadas=True):
    """Lista de herramientas para la API, en orden fijo (el orden estable permite reutilizar la caché)."""
    return [{'name': nombre, 'description': desc, 'input_schema': esquema}
            for nombre, (_, desc, esquema) in HERRAMIENTAS.items()
            if acciones_habilitadas or nombre not in ACCIONES]


def ejecutar(nombre, entrada, user, conversacion):
    """Corre una herramienta con los permisos del usuario. Devuelve (texto_resultado, es_error)."""
    if nombre not in HERRAMIENTAS:
        return _json({'error': f'Herramienta desconocida: {nombre}'}), True
    funcion = HERRAMIENTAS[nombre][0]
    if not isinstance(entrada, dict):
        return _json({'error': 'Parámetros inválidos.'}), True
    try:
        if nombre in ACCIONES:
            resultado = funcion(user, **entrada, conversacion=conversacion)
        else:
            resultado = funcion(user, **entrada)
    except TypeError as e:
        return _json({'error': f'Parámetros inválidos: {e}'}), True
    return resultado, '"error"' in resultado[:20]
