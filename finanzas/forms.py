from django import forms

from .models import CategoriaGasto, Gasto, Presupuesto, Suscripcion, TipoCambio


def _estilo(form):
    for campo in form.fields.values():
        w = campo.widget
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault('class', 'form-check-input')
        else:
            w.attrs.setdefault('class', 'form-select' if isinstance(w, forms.Select) else 'form-control')


def _categorias(form, actual_id):
    form.fields['categoria'].queryset = (CategoriaGasto.objects.filter(activa=True) |
                                         CategoriaGasto.objects.filter(pk=actual_id)).distinct()


class PresupuestoForm(forms.ModelForm):
    class Meta:
        model = Presupuesto
        fields = ['anio', 'categoria', 'monto', 'moneda', 'observaciones']
        widgets = {'observaciones': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _categorias(self, self.instance.categoria_id)
        _estilo(self)

    def clean(self):
        datos = super().clean()
        anio, categoria = datos.get('anio'), datos.get('categoria')
        if anio and categoria and Presupuesto.objects.filter(anio=anio, categoria=categoria).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(f'Ya existe un presupuesto {anio} para {categoria}. Edítalo en vez de crear otro.')
        if anio and not 2000 <= anio <= 2100:
            self.add_error('anio', 'Año fuera de rango.')
        return datos


class GastoForm(forms.ModelForm):
    class Meta:
        model = Gasto
        fields = ['fecha', 'concepto', 'categoria', 'proveedor', 'monto', 'moneda', 'estado', 'presupuesto', 'observaciones']
        widgets = {'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'observaciones': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _categorias(self, self.instance.categoria_id)
        self.fields['presupuesto'].queryset = Presupuesto.objects.select_related('categoria')
        self.fields['presupuesto'].empty_label = 'Automático (año y categoría del gasto)'
        _estilo(self)

    def clean(self):
        datos = super().clean()
        p, fecha = datos.get('presupuesto'), datos.get('fecha')
        if p and fecha and p.anio != fecha.year:
            self.add_error('presupuesto', f'El presupuesto es de {p.anio} y el gasto es de {fecha.year}.')
        return datos


class TipoCambioForm(forms.ModelForm):
    class Meta:
        model = TipoCambio
        fields = ['anio', 'mes', 'crc_por_usd', 'observaciones']
        labels = {'anio': 'Año', 'mes': 'Mes'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mes'].widget = forms.Select(choices=[(m, f'{m:02d}') for m in range(1, 13)])
        _estilo(self)


class SuscripcionForm(forms.ModelForm):
    class Meta:
        model = Suscripcion
        fields = ['nombre', 'proveedor', 'categoria', 'descripcion', 'costo', 'moneda', 'frecuencia', 'fecha_inicio',
                  'proxima_renovacion', 'estado', 'responsable', 'observaciones']
        widgets = {'fecha_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'proxima_renovacion': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'descripcion': forms.Textarea(attrs={'rows': 2}), 'observaciones': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _categorias(self, self.instance.categoria_id)
        _estilo(self)

    def clean(self):
        datos = super().clean()
        if datos.get('estado') == 'activa' and not datos.get('proxima_renovacion'):
            self.add_error('proxima_renovacion', 'Una suscripción activa necesita su próxima renovación.')
        ini, ren = datos.get('fecha_inicio'), datos.get('proxima_renovacion')
        if ini and ren and ren < ini:
            self.add_error('proxima_renovacion', 'La renovación no puede ser antes del inicio.')
        return datos
