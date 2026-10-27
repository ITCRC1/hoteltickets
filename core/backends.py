"""Login con usuario O correo electrónico (sin distinguir mayúsculas)."""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class UsuarioOCorreoBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        username = username.strip()
        user = User.objects.filter(username__iexact=username).first()
        if user is None and '@' in username:
            coincidencias = list(User.objects.filter(email__iexact=username)[:2])
            user = coincidencias[0] if len(coincidencias) == 1 else None  # correo ambiguo → no adivinar
        if user is None:
            User().set_password(password)  # mismo costo de tiempo que un usuario existente
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
