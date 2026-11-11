"""
Tareas del departamento de TI (actividades planificadas, distintas de los tickets que reportan los hoteles).
Se muestran en el calendario por su fecha de vencimiento.
"""
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import EliminacionLogica


class Tarea(EliminacionLogica):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('en_progreso', 'En progreso'),
        ('completada', 'Completada'),
    ]
    ESTADO_COLORES = {'pendiente': 'primary', 'en_progreso': 'info', 'completada': 'success'}
    PRIORIDAD_CHOICES = [
        ('baja', 'Baja'),
        ('normal', 'Normal'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente'),
    ]
    PRIORIDAD_COLORES = {'baja': 'secondary', 'normal': 'info', 'alta': 'warning', 'urgente': 'danger'}
    PRIORIDAD_ORDEN = {'urgente': 0, 'alta': 1, 'normal': 2, 'baja': 3}

    titulo = models.CharField('Título', max_length=200)
    descripcion = models.TextField('Descripción', blank=True)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='pendiente', db_index=True)
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default='normal', db_index=True)
    fecha_vencimiento = models.DateField('Vence', null=True, blank=True, db_index=True)
    responsable = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='tareas_asignadas')
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    completada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = [models.F('fecha_vencimiento').asc(nulls_last=True), '-creado_en']
        indexes = [models.Index(fields=['estado', 'fecha_vencimiento'])]

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return reverse('tarea_editar', args=[self.pk])

    @property
    def color_estado(self):
        return self.ESTADO_COLORES.get(self.estado, 'secondary')

    @property
    def color_prioridad(self):
        return self.PRIORIDAD_COLORES.get(self.prioridad, 'secondary')

    @property
    def vencida(self):
        return bool(self.fecha_vencimiento and self.estado != 'completada'
                    and self.fecha_vencimiento < timezone.localdate())

    def save(self, *args, **kwargs):
        if self.estado == 'completada' and not self.completada_en:
            self.completada_en = timezone.now()
        elif self.estado != 'completada':
            self.completada_en = None
        super().save(*args, **kwargs)

    def resumen_para_auditoria(self):
        vence = self.fecha_vencimiento.strftime('%d/%m/%Y') if self.fecha_vencimiento else 'sin fecha'
        return f'Tarea "{self.titulo}" · {self.get_estado_display()} · {self.get_prioridad_display()} · vence {vence}'
