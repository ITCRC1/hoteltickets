from django import forms
from django.contrib.auth.models import User

from . import roles

ROL_CHOICES = [(r, r) for r in roles.ROLES]


class UsuarioNuevoForm(forms.Form):
    email = forms.EmailField(label='Correo', widget=forms.EmailInput(attrs={'class': 'form-control'}))
    nombre = forms.CharField(label='Nombre', max_length=150,
                             widget=forms.TextInput(attrs={'class': 'form-control'}))
    rol = forms.ChoiceField(label='Rol', choices=ROL_CHOICES, initial=roles.IT,
                            widget=forms.Select(attrs={'class': 'form-select'}))
    departamento = forms.CharField(label='Departamento', max_length=100, required=False,
                                   widget=forms.TextInput(attrs={'class': 'form-control'}))

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('Ya existe un usuario con ese correo.')
        return email


class UsuarioEditarForm(forms.Form):
    nombre = forms.CharField(label='Nombre', max_length=150,
                             widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    rol = forms.ChoiceField(label='Rol', choices=ROL_CHOICES,
                            widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    departamento = forms.CharField(label='Departamento', max_length=100, required=False,
                                   widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    activo = forms.BooleanField(label='Activo', required=False,
                                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))


class DefinirClaveForm(forms.Form):
    password1 = forms.CharField(label='Nueva contraseña', strip=False,
                                widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}))
    password2 = forms.CharField(label='Repite la contraseña', strip=False,
                                widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}))

    def __init__(self, *args, email='', **kwargs):
        super().__init__(*args, **kwargs)
        self.email = email

    def clean(self):
        from .invitaciones import validar_password
        datos = super().clean()
        p1, p2 = datos.get('password1') or '', datos.get('password2') or ''
        if p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        error = validar_password(p1, self.email)
        if error:
            raise forms.ValidationError(error)
        return datos
