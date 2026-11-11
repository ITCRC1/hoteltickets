"""
Modelos transversales de la plataforma de TI:
  - EliminacionLogica: base para la papelera (borrado recuperable) de cualquier módulo.
  - Perfil: datos extra del usuario (departamento) e invitación por link.
  - Directorio: correo → departamento de quien reporta (para derivar el departamento del ticket).
  - Auditoria: bitácora general de todos los módulos (quién, qué, antes/después, cuándo).
"""
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ActivosManager(models.Manager):
    """Manager por defecto: oculta lo que está en la papelera."""
    def get_queryset(self):
        return super().get_queryset().filter(eliminado_en__isnull=True)


class EliminacionLogica(models.Model):
    """Base para registros que van a la papelera en vez de borrarse.

    `objects` excluye lo eliminado; `todos` incluye todo (papelera, auditoría).
    El borrado definitivo es `delete()` normal y solo lo usa la papelera (Administrador).
    """
    eliminado_en = models.DateTimeField(null=True, blank=True, db_index=True)
    eliminado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    objects = ActivosManager()
    todos = models.Manager()

    class Meta:
        abstract = True

    @property
    def en_papelera(self):
        return self.eliminado_en is not None

    def enviar_a_papelera(self, usuario):
        self.eliminado_en, self.eliminado_por = timezone.now(), usuario
        self.save(update_fields=['eliminado_en', 'eliminado_por'])

    def restaurar(self):
        self.eliminado_en, self.eliminado_por = None, None
        self.save(update_fields=['eliminado_en', 'eliminado_por'])


class Directorio(models.Model):
    """Personas que reportan: su correo determina el departamento del ticket (el formulario no lo pregunta)."""
    email = models.EmailField('Correo', unique=True)
    nombre = models.CharField(max_length=150, blank=True)
    departamento = models.CharField(max_length=100)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['email']
        verbose_name = 'Contacto del directorio'
        verbose_name_plural = 'Directorio (correo → departamento)'

    def __str__(self):
        return f'{self.email} · {self.departamento}'

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @staticmethod
    def departamento_de(email):
        """Departamento para un correo: primero el directorio, luego el perfil del usuario con ese correo."""
        email = (email or '').strip().lower()
        if not email:
            return ''
        fila = Directorio.objects.filter(email=email).first()
        if fila:
            return fila.departamento
        perfil = Perfil.objects.filter(usuario__email__iexact=email).exclude(departamento='').first()
        return perfil.departamento if perfil else ''


class Perfil(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    departamento = models.CharField(max_length=100, blank=True)
    # Invitación: solo se guarda la huella SHA-256 del token, nunca el token.
    invite_hash = models.CharField(max_length=64, blank=True, db_index=True)
    invite_exp = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'

    def __str__(self):
        return f'Perfil de {self.usuario}'


class Auditoria(models.Model):
    """Bitácora inmutable de acciones importantes en toda la plataforma."""
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    usuario_nombre = models.CharField(max_length=150, blank=True,
                                      help_text='Se conserva aunque el usuario se borre')
    accion = models.CharField(max_length=40, db_index=True)
    modulo = models.CharField(max_length=40, db_index=True)
    objeto_id = models.CharField(max_length=64, blank=True)
    objeto = models.CharField(max_length=200, blank=True)
    cambios = models.JSONField(default=dict, blank=True,
                               help_text='{"campo": ["antes", "después"]}')
    detalle = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'Registro de auditoría general'
        verbose_name_plural = 'Auditoría general'

    def __str__(self):
        return f'{self.creado_en:%d/%m/%Y %H:%M} · {self.usuario_nombre} · {self.accion} · {self.objeto}'
