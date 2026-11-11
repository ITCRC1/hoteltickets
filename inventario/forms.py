from django import forms

from tickets.models import Hotel

from .models import Activo, CategoriaActivo, EstadoActivo


class ActivoForm(forms.ModelForm):
    class Meta:
        model = Activo
        fields = ['codigo', 'nombre', 'categoria', 'marca', 'modelo', 'numero_serie', 'ubicacion', 'departamento',
                  'responsable', 'estado', 'fecha_adquisicion', 'garantia_hasta', 'observaciones']
        widgets = {
            'fecha_adquisicion': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'garantia_hasta': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'observaciones': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo opciones activas (más la actual, para no perderla al editar).
        actual = self.instance
        self.fields['categoria'].queryset = CategoriaActivo.objects.filter(activa=True) | \
            CategoriaActivo.objects.filter(pk=getattr(actual, 'categoria_id', None))
        self.fields['estado'].queryset = EstadoActivo.objects.filter(activo=True) | \
            EstadoActivo.objects.filter(pk=getattr(actual, 'estado_id', None))
        self.fields['ubicacion'].queryset = Hotel.objects.filter(activo=True) | \
            Hotel.objects.filter(pk=getattr(actual, 'ubicacion_id', None))
        for nombre, campo in self.fields.items():
            clase = 'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'
            campo.widget.attrs.setdefault('class', clase)
        self.fields['codigo'].widget.attrs['placeholder'] = 'Automático si se deja vacío'

    def clean_codigo(self):
        codigo = (self.cleaned_data.get('codigo') or '').strip().upper()
        if codigo and Activo.todos.filter(codigo=codigo).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya existe un activo con ese código (revisa también la papelera).')
        return codigo

    def clean(self):
        datos = super().clean()
        adq, gar = datos.get('fecha_adquisicion'), datos.get('garantia_hasta')
        if adq and gar and gar < adq:
            self.add_error('garantia_hasta', 'La garantía no puede vencer antes de la fecha de adquisición.')
        return datos
