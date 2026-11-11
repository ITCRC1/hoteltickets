from django.urls import path

from . import views

urlpatterns = [
    path('inventario/', views.activo_lista, name='activo_lista'),
    path('inventario/nuevo/', views.activo_crear, name='activo_crear'),
    path('inventario/<int:pk>/', views.activo_editar, name='activo_editar'),
    path('inventario/<int:pk>/eliminar/', views.activo_eliminar, name='activo_eliminar'),
]
