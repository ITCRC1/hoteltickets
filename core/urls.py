from django.urls import path

from . import configuracion, views

urlpatterns = [
    path('accounts/login/', views.Ingresar.as_view(), name='login'),
    path('accounts/logout/', views.Salir.as_view(), name='logout'),
    path('invitacion/<str:token>/', views.invitacion, name='invitacion'),
    path('usuarios/', views.usuarios, name='usuarios'),
    path('usuarios/<int:pk>/editar/', views.usuario_editar, name='usuario_editar'),
    path('usuarios/<int:pk>/invitar/', views.usuario_invitar, name='usuario_invitar'),
    path('auditoria/', views.auditoria, name='auditoria'),
    path('configuracion/', configuracion.configuracion, name='configuracion'),
    path('configuracion/<str:nombre>/', configuracion.catalogo, name='catalogo'),
    path('configuracion/<str:nombre>/<int:pk>/', configuracion.catalogo, name='catalogo_editar'),
    path('configuracion/<str:nombre>/<int:pk>/borrar/', configuracion.catalogo_borrar, name='catalogo_borrar'),
    path('papelera/', views.papelera, name='papelera'),
    path('papelera/<str:clave_modelo>/<int:pk>/restaurar/', views.papelera_restaurar, name='papelera_restaurar'),
    path('papelera/<str:clave_modelo>/<int:pk>/eliminar/', views.papelera_purgar, name='papelera_purgar'),
]
