"""
Inventario tecnológico. Las categorías y los estados son tablas (ampliables desde la administración);
la ubicación es la misma tabla que usan los tickets (hoteles y puntos externos).
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import EliminacionLogica
from tickets.models import Hotel

GARANTIA_AVISO_DIAS = 90


class CategoriaActivo(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Categoría de activo'
        verbose_name_plural = 'Categorías de activos'

    def __str__(self):
        return self.nombre


class EstadoActivo(models.Model):
    COLORES = [('success', 'Verde'), ('info', 'Celeste'), ('warning', 'Amarillo'), ('danger', 'Rojo'),
               ('secondary', 'Gris'), ('primary', 'Azul')]
    nombre = models.CharField(max_length=40, unique=True)
    color = models.CharField(max_length=12, choices=COLORES, default='secondary')
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Estado de activo'
        verbose_name_plural = 'Estados de activos'

    def __str__(self):
        return self.nombre


class Activo(EliminacionLogica):
    codigo = models.CharField('Código', max_length=30, unique=True, blank=True,
                              help_text='Identificador del activo. Si se deja vacío se asigna TI-00001, TI-00002…')
    nombre = models.CharField('Nombre del equipo', max_length=150)
    categoria = models.ForeignKey(CategoriaActivo, on_delete=models.PROTECT, related_name='activos')
    marca = models.CharField(max_length=80, blank=True)
    modelo = models.CharField(max_length=80, blank=True)
    numero_serie = models.CharField('Número de serie', max_length=100, blank=True, db_index=True)
    ubicacion = models.ForeignKey(Hotel, on_delete=models.PROTECT, related_name='activos', verbose_name='Ubicación')
    departamento = models.CharField(max_length=100, blank=True)
    responsable = models.CharField(max_length=150, blank=True, help_text='Persona que tiene el equipo a cargo')
    estado = models.ForeignKey(EstadoActivo, on_delete=models.PROTECT, related_name='activos')
    fecha_adquisicion = models.DateField('Fecha de adquisición', null=True, blank=True)
    garantia_hasta = models.DateField('Garantía hasta', null=True, blank=True)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Activo'
        verbose_name_plural = 'Activos'

    def __str__(self):
        return f'{self.codigo} · {self.nombre}'

    def get_absolute_url(self):
        return reverse('activo_editar', args=[self.pk])

    def save(self, *args, **kwargs):
        self.codigo = (self.codigo or '').strip().upper()
        super().save(*args, **kwargs)
        if not self.codigo:
            self.codigo = f'TI-{self.pk:05d}'
            type(self).todos.filter(pk=self.pk).update(codigo=self.codigo)

    @property
    def estado_garantia(self):
        """'vencida', 'por_vencer' (≤ 90 días), 'vigente' o '' si no tiene."""
        if not self.garantia_hasta:
            return ''
        hoy = timezone.localdate()
        if self.garantia_hasta < hoy:
            return 'vencida'
        if self.garantia_hasta <= hoy + timedelta(days=GARANTIA_AVISO_DIAS):
            return 'por_vencer'
        return 'vigente'

    def resumen_para_auditoria(self):
        return (f'{self.codigo} {self.nombre} · {self.categoria} · {self.marca} {self.modelo} · serie '
                f'{self.numero_serie or "—"} · {self.ubicacion} · {self.estado}')
