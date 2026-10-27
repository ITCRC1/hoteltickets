"""
Vistas de la plataforma: login/salida, invitación, usuarios y auditoría general.
"""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import invitaciones, roles
from .auditoria import auditar
from .forms import DefinirClaveForm, UsuarioEditarForm, UsuarioNuevoForm
from .models import Auditoria

# Cookie que solo dice "esta computadora tenía sesión": si vuelve al login sin sesión, la sesión expiró.
COOKIE_SESION = 'tk_sesion'
UN_ANO = 365 * 24 * 3600


def _marcar_sesion(response):
    response.set_cookie(COOKIE_SESION, '1', max_age=UN_ANO, httponly=True, samesite='Lax')
    return response


# ------------------ acceso ------------------

class Ingresar(auth_views.LoginView):
    template_name = 'registration/login.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sesion_expirada'] = (self.request.method == 'GET' and 'next' in self.request.GET
                                  and self.request.COOKIES.get(COOKIE_SESION) == '1')
        return ctx

    def form_valid(self, form):
        return _marcar_sesion(super().form_valid(form))


class Salir(auth_views.LogoutView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        response.delete_cookie(COOKIE_SESION)
        return response


def invitacion(request, token):
    """Link de invitación: la persona define su contraseña y entra."""
    user = invitaciones.usuario_por_token(token)
    if user is None:
        return render(request, 'core/invitacion_invalida.html', status=400)
    form = DefinirClaveForm(request.POST or None, email=user.email)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user.set_password(form.cleaned_data['password1'])
            user.save(update_fields=['password'])
            invitaciones.consumir(user)
            auditar(request, 'INVITACION_ACEPTADA', 'usuarios', objeto=user, usuario=user)
        login(request, user, backend='core.backends.UsuarioOCorreoBackend')
        messages.success(request, f'¡Bienvenido, {user.get_full_name() or user.email}! Tu contraseña quedó guardada.')
        return _marcar_sesion(redirect('dashboard'))
    return render(request, 'core/invitacion.html', {'form': form, 'invitado': user})


# ------------------ usuarios (solo Administrador) ------------------

def _link(request, token):
    return request.build_absolute_uri(reverse('invitacion', args=[token]))


def _admins_activos():
    return User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(groups__name=roles.ADMIN)).distinct()


@roles.requiere_rol(roles.ADMIN)
def usuarios(request):
    form_nuevo = UsuarioNuevoForm(request.POST or None)
    if request.method == 'POST' and form_nuevo.is_valid():
        d = form_nuevo.cleaned_data
        with transaction.atomic():
            partes = d['nombre'].strip().split(' ', 1)
            user = User(username=d['email'], email=d['email'],
                        first_name=partes[0][:150], last_name=(partes[1] if len(partes) > 1 else '')[:150])
            user.set_unusable_password()
            user.save()
            roles.asignar_rol(user, d['rol'])
            perfil = invitaciones.perfil_de(user)
            perfil.departamento = d['departamento']
            perfil.save(update_fields=['departamento', 'actualizado_en'])
            token = invitaciones.invitar(user)
            auditar(request, 'USUARIO_CREADO', 'usuarios', objeto=user,
                    detalle=f"Rol: {d['rol']} · Departamento: {d['departamento'] or '—'}")
        request.session['link_invitacion'] = {'email': user.email, 'nombre': user.get_full_name(),
                                              'url': _link(request, token), 'dias': invitaciones.INVITE_DIAS}
        return redirect('usuarios')

    lista = []
    for u in User.objects.select_related('perfil').prefetch_related('groups').order_by('-is_active', 'first_name', 'username'):
        perfil = getattr(u, 'perfil', None)
        lista.append({'u': u, 'rol': roles.rol_asignado(u) or '—',
                      'departamento': perfil.departamento if perfil else '',
                      'pendiente': invitaciones.pendiente(perfil),
                      'form': UsuarioEditarForm(prefix=f'u{u.pk}', initial={
                          'nombre': u.get_full_name() or u.username,
                          'rol': roles.rol_asignado(u) or roles.LECTURA,
                          'departamento': perfil.departamento if perfil else '',
                          'activo': u.is_active})})
    return render(request, 'core/usuarios.html', {
        'form_nuevo': form_nuevo, 'lista': lista, 'roles': roles.ROLES,
        'link': request.session.pop('link_invitacion', None),
    })


@require_POST
@roles.requiere_rol(roles.ADMIN)
def usuario_editar(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UsuarioEditarForm(request.POST, prefix=f'u{pk}')
    if not form.is_valid():
        messages.error(request, 'Revisa los datos del usuario.')
        return redirect('usuarios')
    d = form.cleaned_data
    rol_antes, activo_antes = roles.rol_asignado(user), user.is_active
    # Salvaguardas: nadie se quita a sí mismo el acceso, y siempre queda al menos un Administrador activo.
    if user == request.user and (not d['activo'] or d['rol'] != roles.ADMIN):
        messages.error(request, 'No puedes quitarte tu propio rol de Administrador ni desactivarte.')
        return redirect('usuarios')
    if rol_antes == roles.ADMIN and (d['rol'] != roles.ADMIN or not d['activo']) \
            and not _admins_activos().exclude(pk=user.pk).exists():
        messages.error(request, 'Debe quedar al menos un Administrador activo.')
        return redirect('usuarios')

    perfil = invitaciones.perfil_de(user)
    nombre_antes, depto_antes = user.get_full_name() or user.username, perfil.departamento
    with transaction.atomic():
        partes = d['nombre'].strip().split(' ', 1)
        user.first_name, user.last_name = partes[0][:150], (partes[1] if len(partes) > 1 else '')[:150]
        user.is_active = d['activo']
        user.save(update_fields=['first_name', 'last_name', 'is_active'])
        if d['rol'] != rol_antes:
            roles.asignar_rol(user, d['rol'])
        perfil.departamento = d['departamento']
        perfil.save(update_fields=['departamento', 'actualizado_en'])
        cambios = {'nombre': [nombre_antes, user.get_full_name()], 'rol': [rol_antes, d['rol']],
                   'departamento': [depto_antes, d['departamento']],
                   'activo': ['sí' if activo_antes else 'no', 'sí' if d['activo'] else 'no']}
        if any(a != b for a, b in cambios.values()):
            auditar(request, 'USUARIO_EDITADO', 'usuarios', objeto=user, cambios=cambios)
            messages.success(request, f'Usuario {user.email or user.username} actualizado.')
        else:
            messages.info(request, 'Sin cambios.')
    return redirect('usuarios')


@require_POST
@roles.requiere_rol(roles.ADMIN)
def usuario_invitar(request, pk):
    user = get_object_or_404(User, pk=pk, is_active=True)
    token = invitaciones.invitar(user)
    auditar(request, 'INVITACION_GENERADA', 'usuarios', objeto=user)
    request.session['link_invitacion'] = {'email': user.email or user.username, 'nombre': user.get_full_name(),
                                          'url': _link(request, token), 'dias': invitaciones.INVITE_DIAS}
    return redirect('usuarios')


# ------------------ auditoría general (solo Administrador) ------------------

@roles.requiere_rol(roles.ADMIN)
def auditoria(request):
    qs = Auditoria.objects.all()
    modulo, accion, buscar = request.GET.get('modulo', ''), request.GET.get('accion', ''), request.GET.get('q', '').strip()
    if modulo:
        qs = qs.filter(modulo=modulo)
    if accion:
        qs = qs.filter(accion=accion)
    if buscar:
        qs = qs.filter(Q(usuario_nombre__icontains=buscar) | Q(objeto__icontains=buscar) | Q(detalle__icontains=buscar))
    pagina = Paginator(qs, 50).get_page(request.GET.get('page'))
    return render(request, 'core/auditoria.html', {
        'pagina': pagina, 'total': qs.count(),
        'modulos': Auditoria.objects.order_by('modulo').values_list('modulo', flat=True).distinct(),
        'acciones': Auditoria.objects.order_by('accion').values_list('accion', flat=True).distinct(),
        'filtros': {'modulo': modulo, 'accion': accion, 'q': buscar},
    })
