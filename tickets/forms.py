from django import forms
from .models import Ticket, Comentario, Hotel


class TicketPublicoForm(forms.ModelForm):
    """
    Formulario público — el que llena el staff de hoteles sin necesidad de login.

    El campo ‘titulo’ se guarda desde el select público y la opción de texto
    libre "Otra incidencia...".
    """

    class Meta:
        model = Ticket
        fields = [
            'hotel',
            # 'categoria',   # ← oculto temporalmente (ver nota arriba)
            'titulo', 'descripcion',
            'solicitante_nombre', 'solicitante_email',
        ]
        widgets = {
            'hotel': forms.Select(attrs={'class': 'form-select form-select-lg'}),
            # 'categoria': forms.Select(attrs={'class': 'form-select form-select-lg'}),
            'titulo': forms.HiddenInput(),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Describe el problema con el mayor detalle posible: qué pasa, desde cuándo, qué se intentó.',
            }),
            'solicitante_nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tu nombre completo',
            }),
            'solicitante_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo@hotel.com',
            }),
        }
        labels = {
            'hotel': 'Ubicación',
            'titulo': 'Título del reporte',
            'descripcion': 'Descripción detallada',
            'solicitante_nombre': 'Tu nombre',
            'solicitante_email': 'Tu correo electrónico',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hotel'].queryset = Hotel.objects.filter(activo=True)


class TicketGestionForm(forms.ModelForm):
    """Formulario interno para gestionar un ticket (estado, asignación, etc).
    AQUÍ SÍ se conserva la categoría — el equipo interno puede reclasificarla."""

    class Meta:
        model = Ticket
        fields = ['estado', 'prioridad', 'asignado_a', 'categoria']
        widgets = {
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'prioridad': forms.Select(attrs={'class': 'form-select'}),
            'asignado_a': forms.Select(attrs={'class': 'form-select'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
        }


class ComentarioForm(forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['contenido', 'interno']
        widgets = {
            'contenido': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Escribe una actualización, lo que hiciste, o una nota...',
            }),
            'interno': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'contenido': 'Comentario / Actualización',
            'interno': 'Nota interna (no visible para el solicitante)',
        }
