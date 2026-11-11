"""
Finanzas de TI: presupuestos anuales por categoría, gastos, tipo de cambio mensual y suscripciones.

Reglas de dinero (decisión del Controller, 2026-10-27):
  - Cada monto conserva su moneda original (CRC o USD).
  - Un único tipo de cambio por mes (tabla de validación, se registra a mano).
  - Nunca se suman monedas distintas sin convertir: un gasto en otra moneda se convierte con el tipo de
    cambio del mes de su fecha; si ese mes no tiene tipo, el gasto queda FUERA de los totales y se avisa.
  - Un presupuesto anual en otra moneda se convierte con el promedio de los tipos registrados de ese año.
  - Cálculos con Decimal y redondeo a 2 decimales (ROUND_HALF_UP).
"""
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Avg, Q

from core.models import EliminacionLogica

USD, CRC = 'USD', 'CRC'
MONEDAS = [(USD, 'USD — Dólares'), (CRC, 'CRC — Colones')]
SIMBOLO = {USD: '$', CRC: '₡'}
CENTAVO = Decimal('0.01')


def redondear(valor):
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class TipoCambio(models.Model):
    """Tabla mensual de validación: colones por dólar, uno por mes."""
    anio = models.PositiveSmallIntegerField('Año')
    mes = models.PositiveSmallIntegerField(choices=[(m, m) for m in range(1, 13)])
    crc_por_usd = models.DecimalField('Colones por dólar', max_digits=10, decimal_places=4,
                                      validators=[MinValueValidator(Decimal('0.0001'))])
    observaciones = models.CharField(max_length=200, blank=True)
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-anio', '-mes']
        constraints = [models.UniqueConstraint(fields=['anio', 'mes'], name='un_tipo_de_cambio_por_mes')]
        verbose_name = 'Tipo de cambio mensual'
        verbose_name_plural = 'Tipos de cambio mensuales'

    def __str__(self):
        return f'{self.mes:02d}/{self.anio}: ₡{self.crc_por_usd}'

    @staticmethod
    def del_mes(anio, mes):
        fila = TipoCambio.objects.filter(anio=anio, mes=mes).first()
        return fila.crc_por_usd if fila else None

    @staticmethod
    def promedio_del_anio(anio):
        valor = TipoCambio.objects.filter(anio=anio).aggregate(p=Avg('crc_por_usd'))['p']
        return Decimal(valor).quantize(Decimal('0.0001')) if valor is not None else None


def convertir(monto, de, a, tipo):
    """Convierte con un tipo de cambio explícito (colones por dólar). Devuelve None si hace falta tipo y no hay."""
    monto = Decimal(monto)
    if de == a:
        return redondear(monto)
    if not tipo:
        return None
    if de == CRC and a == USD:
        return redondear(monto / tipo)
    return redondear(monto * tipo)


class CategoriaGasto(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Categoría de presupuesto/gasto'
        verbose_name_plural = 'Categorías de presupuesto/gasto'

    def __str__(self):
        return self.nombre


class Presupuesto(EliminacionLogica):
    anio = models.PositiveSmallIntegerField('Año', db_index=True)
    categoria = models.ForeignKey(CategoriaGasto, on_delete=models.PROTECT, related_name='presupuestos')
    monto = models.DecimalField('Monto asignado', max_digits=14, decimal_places=2,
                                validators=[MinValueValidator(Decimal('0'))])
    moneda = models.CharField(max_length=3, choices=MONEDAS, default=USD)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-anio', 'categoria__nombre']
        constraints = [models.UniqueConstraint(fields=['anio', 'categoria'], condition=Q(eliminado_en__isnull=True),
                                               name='un_presupuesto_por_categoria_y_anio')]

    def __str__(self):
        return f'Presupuesto {self.anio} · {self.categoria}'

    def monto_en(self, moneda):
        return convertir(self.monto, self.moneda, moneda, TipoCambio.promedio_del_anio(self.anio))

    def resumen_para_auditoria(self):
        return f'{self} · {SIMBOLO[self.moneda]}{self.monto:,.2f} {self.moneda}'


class Gasto(EliminacionLogica):
    ESTADO_CHOICES = [('pendiente', 'Pendiente de pago'), ('pagado', 'Pagado'), ('anulado', 'Anulado')]
    ESTADO_COLORES = {'pendiente': 'warning', 'pagado': 'success', 'anulado': 'secondary'}

    fecha = models.DateField(db_index=True)
    concepto = models.CharField(max_length=200)
    categoria = models.ForeignKey(CategoriaGasto, on_delete=models.PROTECT, related_name='gastos')
    proveedor = models.CharField(max_length=120, blank=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    moneda = models.CharField(max_length=3, choices=MONEDAS, default=USD)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pagado', db_index=True)
    presupuesto = models.ForeignKey(Presupuesto, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='gastos', help_text='Si se deja vacío se asocia al presupuesto del '
                                                                     'año y categoría del gasto')
    suscripcion = models.ForeignKey('Suscripcion', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='pagos')
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha', '-creado_en']

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y} · {self.concepto}'

    @property
    def color_estado(self):
        return self.ESTADO_COLORES.get(self.estado, 'secondary')

    @property
    def tipo_cambio(self):
        return TipoCambio.del_mes(self.fecha.year, self.fecha.month)

    def monto_en(self, moneda):
        """Monto convertido con el tipo del mes del gasto; None si hace falta tipo y no está registrado."""
        return convertir(self.monto, self.moneda, moneda, self.tipo_cambio)

    def save(self, *args, **kwargs):
        if self.presupuesto_id is None:
            self.presupuesto = Presupuesto.objects.filter(anio=self.fecha.year, categoria_id=self.categoria_id).first()
        super().save(*args, **kwargs)

    def resumen_para_auditoria(self):
        return f'{self} · {self.categoria} · {SIMBOLO[self.moneda]}{self.monto:,.2f} {self.moneda} · {self.get_estado_display()}'


class Suscripcion(EliminacionLogica):
    FRECUENCIAS = [('mensual', 'Mensual'), ('trimestral', 'Trimestral'), ('semestral', 'Semestral'), ('anual', 'Anual')]
    MESES_POR_FRECUENCIA = {'mensual': 1, 'trimestral': 3, 'semestral': 6, 'anual': 12}
    ESTADO_CHOICES = [('activa', 'Activa'), ('pausada', 'Pausada'), ('cancelada', 'Cancelada')]
    ESTADO_COLORES = {'activa': 'success', 'pausada': 'warning', 'cancelada': 'secondary'}

    nombre = models.CharField('Servicio', max_length=150)
    proveedor = models.CharField(max_length=120, blank=True)
    descripcion = models.TextField(blank=True)
    categoria = models.ForeignKey(CategoriaGasto, on_delete=models.PROTECT, related_name='suscripciones',
                                  help_text='Relaciona la suscripción con el presupuesto de esa categoría')
    costo = models.DecimalField('Costo por período', max_digits=14, decimal_places=2,
                                validators=[MinValueValidator(Decimal('0'))])
    moneda = models.CharField(max_length=3, choices=MONEDAS, default=USD)
    frecuencia = models.CharField(max_length=12, choices=FRECUENCIAS, default='mensual')
    fecha_inicio = models.DateField('Inicio', null=True, blank=True)
    proxima_renovacion = models.DateField('Próxima renovación', null=True, blank=True, db_index=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='activa', db_index=True)
    responsable = models.CharField(max_length=150, blank=True)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [models.F('proxima_renovacion').asc(nulls_last=True), 'nombre']
        verbose_name = 'Suscripción'
        verbose_name_plural = 'Suscripciones'

    def __str__(self):
        return f'{self.nombre}' + (f' ({self.proveedor})' if self.proveedor else '')

    @property
    def color_estado(self):
        return self.ESTADO_COLORES.get(self.estado, 'secondary')

    @property
    def meses_periodo(self):
        return self.MESES_POR_FRECUENCIA[self.frecuencia]

    @property
    def costo_mensual(self):
        return redondear(self.costo / self.meses_periodo)

    @property
    def costo_anual(self):
        return redondear(self.costo * 12 / self.meses_periodo)

    def resumen_para_auditoria(self):
        return f'{self} · {SIMBOLO[self.moneda]}{self.costo:,.2f} {self.moneda} {self.get_frecuencia_display().lower()}'
