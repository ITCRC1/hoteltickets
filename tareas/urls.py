from django.urls import path

from . import views

urlpatterns = [
    path('tareas/', views.tarea_lista, name='tarea_lista'),
    path('tareas/nueva/', views.tarea_crear, name='tarea_crear'),
    path('tareas/<int:pk>/', views.tarea_editar, name='tarea_editar'),
    path('tareas/<int:pk>/estado/', views.tarea_estado, name='tarea_estado'),
    path('tareas/<int:pk>/eliminar/', views.tarea_eliminar, name='tarea_eliminar'),
    path('calendario/', views.calendario, name='calendario'),
    path('calendario/<str:vista>/', views.calendario, name='calendario_vista'),
]
