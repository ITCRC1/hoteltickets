"""
Modelos del sistema de tickets.

Diseño pensado para:
- Múltiples hoteles
- Trazabilidad completa de cada acción (auditoría)
- Métricas de desempeño (tiempos de respuesta y resolución)
"""
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone


class Hotel(models.Model):
    """Cada propiedad/hotel del grupo."""
    nombre = models.CharField(max_length=100, unique=True)
    ubicacion = models.CharField('Ubicación', max_length=200, blank=True)
    oficina = models.CharField('Oficina', max_length=100, blank=True)
    contacto_principal = models.CharField(max_length=100, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Hotel'
        verbose_name_plural = 'Hoteles'

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    """Tipo de incidencia: mantenimiento, IT, limpieza, etc."""
    nombre = models.CharField(max_length=80, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    color = models.CharField(
        max_length=7,
        default='#6c757d',
        help_text='Color hex (ej. #0d6efd) para la etiqueta visual'
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.nombre


class Ticket(models.Model):
    """Una incidencia o solicitud reportada."""

    ESTADO_CHOICES = [
        ('abierto', 'Abierto'),
        ('en_progreso', 'En progreso'),
        ('en_espera', 'En espera'),
        ('resuelto', 'Resuelto'),
        ('cerrado', 'Cerrado'),
    ]
    ESTADO_COLORES = {
        'abierto': 'primary',
        'en_progreso': 'info',
        'en_espera': 'warning',
        'resuelto': 'success',
        'cerrado': 'secondary',
    }

    # Información básica
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(help_text='Describe lo más detalladamente posible')
    hotel = models.ForeignKey(Hotel, on_delete=models.PROTECT, related_name='tickets')
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='tickets')
    ubicacion_especifica = models.CharField(
        max_length=200, blank=True,
        help_text='Ej: Habitación 305, lobby, restaurante, área de piscina'
    )

    # Clasificación
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='abierto', db_index=True)

    # Personas
    solicitante_nombre = models.CharField(
        max_length=100,
        help_text='Nombre de quien reporta (si no tiene cuenta)'
    )
    solicitante_email = models.EmailField(
        help_text='Correo del solicitante para notificaciones',
        default='',
    )
    asignado_a = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tickets_asignados'
    )

    # Tiempos (clave para mostrar tu trabajo)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    primera_respuesta_en = models.DateTimeField(null=True, blank=True)
    resuelto_en = models.DateTimeField(null=True, blank=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creado_en']
        indexes = [
            models.Index(fields=['estado', '-creado_en']),
            models.Index(fields=['hotel', 'estado']),
        ]

    def __str__(self):
        return f'#{self.id} · {self.titulo}'

    def get_absolute_url(self):
        return reverse('ticket_detalle', kwargs={'pk': self.pk})

    @property
    def color_estado(self):
        return self.ESTADO_COLORES.get(self.estado, 'secondary')

    @property
    def esta_abierto(self):
        return self.estado not in ('resuelto', 'cerrado')

    def tiempo_respuesta(self):
        """Tiempo desde creación hasta primera respuesta."""
        if self.primera_respuesta_en:
            return self.primera_respuesta_en - self.creado_en
        return None

    def tiempo_resolucion(self):
        """Tiempo desde creación hasta resolución."""
        if self.resuelto_en:
            return self.resuelto_en - self.creado_en
        return None


class Comentario(models.Model):
    """Mensajes y actualizaciones en un ticket."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(User, on_delete=models.PROTECT)
    contenido = models.TextField()
    interno = models.BooleanField(
        default=False,
        help_text='Si está marcado, solo lo ven los técnicos (no el solicitante)'
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_en']

    def __str__(self):
        return f'Comentario de {self.autor} en {self.ticket}'


class RegistroAuditoria(models.Model):
    """
    Bitácora inmutable de cada acción en un ticket.
    Esta es la 'evidencia' de tu trabajo: quién hizo qué y cuándo.
    """
    ACCION_CHOICES = [
        ('crear', 'Ticket creado'),
        ('editar', 'Datos editados'),
        ('cambio_estado', 'Cambio de estado'),
        ('asignar', 'Asignación'),
        ('comentar', 'Comentario añadido'),
        ('resolver', 'Resuelto'),
        ('cerrar', 'Cerrado'),
        ('reabrir', 'Reabierto'),
    ]

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='auditoria')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    usuario_nombre = models.CharField(
        max_length=150, blank=True,
        help_text='Se guarda el nombre por si el usuario se borra después'
    )
    accion = models.CharField(max_length=20, choices=ACCION_CHOICES)
    detalle = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Registros de auditoría'

    def __str__(self):
        return f'{self.get_accion_display()} · {self.ticket} · {self.creado_en:%d/%m/%Y %H:%M}'

    @classmethod
    def registrar(cls, ticket, accion, usuario=None, detalle=''):
        """Helper para crear entradas de auditoría desde las vistas."""
        return cls.objects.create(
            ticket=ticket,
            usuario=usuario,
            usuario_nombre=usuario.get_full_name() or usuario.username if usuario else 'Sistema',
            accion=accion,
            detalle=detalle,
        )
