from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from core import roles

from .models import Tarea


class TareaForm(forms.ModelForm):
    class Meta:
        model = Tarea
        fields = ['titulo', 'descripcion', 'estado', 'prioridad', 'fecha_vencimiento', 'responsable']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'fecha_vencimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'responsable': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Responsable: quien atiende (Administrador / IT Support activos), conservando al actual.
        atienden = User.objects.filter(is_active=True).filter(
            Q(is_superuser=True) | Q(groups__name__in=[roles.ADMIN, roles.IT])).distinct()
        if self.instance.responsable_id:
            atienden = User.objects.filter(Q(pk__in=atienden.values('pk')) | Q(pk=self.instance.responsable_id))
        self.fields['responsable'].queryset = atienden.order_by('first_name', 'username')
        self.fields['responsable'].label_from_instance = lambda u: u.get_full_name() or u.username
        self.fields['responsable'].empty_label = 'Sin responsable'
