from django.urls import path

from . import views

urlpatterns = [
    path('accounts/login/', views.Ingresar.as_view(), name='login'),
    path('accounts/logout/', views.Salir.as_view(), name='logout'),
    path('invitacion/<str:token>/', views.invitacion, name='invitacion'),
    path('usuarios/', views.usuarios, name='usuarios'),
    path('usuarios/<int:pk>/editar/', views.usuario_editar, name='usuario_editar'),
    path('usuarios/<int:pk>/invitar/', views.usuario_invitar, name='usuario_invitar'),
    path('auditoria/', views.auditoria, name='auditoria'),
]
