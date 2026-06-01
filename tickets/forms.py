from django import forms
from .models import Ticket, Comentario, Hotel, Categoria


class TicketPublicoForm(forms.ModelForm):
    """
    Formulario público — el que llena el staff de hoteles SIN necesidad de login.

    Nota: por ahora el sistema solo se usa para el área de TI, así que el campo
    'categoria' está oculto. En la vista `ticket_publico` se asigna automáticamente
    a "IT / Sistemas".

    Para volver a mostrar la categoría cuando se sume otra área:
      1. Añade 'categoria' a la lista de fields de abajo.
      2. Añade su widget al diccionario widgets.
      3. Descomenta el filtro de queryset en __init__.
      4. En el template ticket_publico.html, restaura el bloque del campo.
      5. Quita la asignación automática en views.ticket_publico.
    """

    class Meta:
        model = Ticket
        fields = [
            'hotel',
            # 'categoria',   # ← oculto temporalmente (ver nota arriba)
            'prioridad',
            'titulo', 'descripcion',
            'ubicacion_especifica',
            'solicitante_nombre', 'solicitante_email',
        ]
        widgets = {
            'hotel': forms.Select(attrs={'class': 'form-select form-select-lg'}),
            # 'categoria': forms.Select(attrs={'class': 'form-select form-select-lg'}),
            'prioridad': forms.Select(attrs={'class': 'form-select form-select-lg'}),
            'titulo': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Resumen breve. Ej: "PC de recepción no enciende"',
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Describe el problema con el mayor detalle posible: qué pasa, desde cuándo, qué se intentó.',
            }),
            'ubicacion_especifica': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Recepción, oficina administrativa, habitación 305',
            }),
            'solicitante_nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Tu nombre completo',
            }),
            'solicitante_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo@hotel.com (opcional, para notificarte)',
            }),
        }
        labels = {
            'titulo': 'Título del reporte',
            'descripcion': 'Descripción detallada',
            'ubicacion_especifica': 'Ubicación específica',
            'solicitante_nombre': 'Tu nombre',
            'solicitante_email': 'Tu correo (opcional)',
            'prioridad': '¿Qué tan urgente es?',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hotel'].queryset = Hotel.objects.filter(activo=True)
        # self.fields['categoria'].queryset = Categoria.objects.filter(activa=True)


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
