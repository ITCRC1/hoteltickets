from django.urls import path

from . import views

urlpatterns = [
    path('reportes/', views.reportes, name='reportes'),
    path('reportes/inventario.xlsx', views.exportar_inventario, name='exportar_inventario'),
    path('reportes/tickets.xlsx', views.exportar_tickets, name='exportar_tickets'),
    path('reportes/tareas.xlsx', views.exportar_tareas, name='exportar_tareas'),
]
