from django.urls import path

from . import views

urlpatterns = [
    path('asistente/', views.asistente, name='asistente'),
    path('asistente/enviar/', views.enviar, name='asistente_enviar'),
    path('asistente/<int:pk>/', views.asistente, name='asistente_conversacion'),
    path('asistente/<int:pk>/enviar/', views.enviar, name='asistente_enviar_conversacion'),
    path('asistente/<int:pk>/borrar/', views.conversacion_borrar, name='asistente_borrar'),
    path('asistente/accion/<int:pk>/<str:decision>/', views.accion_resolver, name='asistente_accion'),
    path('asistente/configuracion/', views.configuracion_ia, name='configuracion_ia'),
]
