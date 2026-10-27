"""
Modelos transversales de la plataforma de TI:
  - Perfil: datos extra del usuario (departamento) e invitación por link.
  - Auditoria: bitácora general de todos los módulos (quién, qué, antes/después, cuándo).
"""
from django.contrib.auth.models import User
from django.db import models


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
