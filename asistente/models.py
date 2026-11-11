"""
Asistente de IA (Claude). Cada conversación es de un usuario y solo ese usuario la ve.

`Mensaje.contenido` guarda los bloques EXACTAMENTE como los devolvió la API (incluidos los de razonamiento):
el modelo exige recibirlos sin cambios en el turno siguiente, así que el historial es de solo anexar.
`AccionPendiente` guarda lo que Claude propone modificar; nada se escribe hasta que el usuario confirma.
"""
from django.contrib.auth.models import User
from django.db import models


class Conversacion(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversaciones_ia')
    titulo = models.CharField(max_length=120, default='Nueva conversación')
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-actualizada_en']
        verbose_name = 'Conversación con el asistente'
        verbose_name_plural = 'Conversaciones con el asistente'

    def __str__(self):
        return self.titulo


class Mensaje(models.Model):
    ROLES = [('user', 'Usuario'), ('assistant', 'Asistente')]
    conversacion = models.ForeignKey(Conversacion, on_delete=models.CASCADE, related_name='mensajes')
    rol = models.CharField(max_length=10, choices=ROLES)
    contenido = models.JSONField(help_text='Bloques de contenido tal como se envían/reciben de la API')
    texto = models.TextField(blank=True, help_text='Lo que se muestra en pantalla')
    visible = models.BooleanField(default=True, help_text='False para resultados de herramientas y avisos internos')
    modelo = models.CharField(max_length=60, blank=True)
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    tokens_cache = models.PositiveIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_en', 'pk']


class AccionPendiente(models.Model):
    ESTADOS = [('pendiente', 'Pendiente'), ('confirmada', 'Confirmada'), ('rechazada', 'Rechazada'), ('error', 'Error')]
    conversacion = models.ForeignKey(Conversacion, on_delete=models.CASCADE, related_name='acciones')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    tipo = models.CharField(max_length=40)
    datos = models.JSONField()
    resumen = models.TextField()
    estado = models.CharField(max_length=12, choices=ESTADOS, default='pendiente')
    resultado = models.TextField(blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    resuelta_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['creada_en']
