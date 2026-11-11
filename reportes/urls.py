from django.urls import path

from . import views

urlpatterns = [
    path('reportes/', views.reportes, name='reportes'),
    path('reportes/inventario.xlsx', views.exportar_inventario, name='exportar_inventario'),
    path('reportes/tickets.xlsx', views.exportar_tickets, name='exportar_tickets'),
    path('reportes/tareas.xlsx', views.exportar_tareas, name='exportar_tareas'),
    path('reportes/presupuesto.xlsx', views.exportar_presupuesto, name='exportar_presupuesto'),
    path('reportes/gastos.xlsx', views.exportar_gastos, name='exportar_gastos'),
    path('reportes/suscripciones.xlsx', views.exportar_suscripciones, name='exportar_suscripciones'),
]
