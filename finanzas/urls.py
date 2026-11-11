from django.urls import path

from . import views

urlpatterns = [
    path('presupuestos/', views.presupuesto_resumen, name='presupuesto_resumen'),
    path('presupuestos/nuevo/', views.presupuesto_form, name='presupuesto_crear'),
    path('presupuestos/<int:pk>/', views.presupuesto_form, name='presupuesto_editar'),
    path('presupuestos/<int:pk>/eliminar/', views.presupuesto_eliminar, name='presupuesto_eliminar'),
    path('gastos/', views.gasto_lista, name='gasto_lista'),
    path('gastos/nuevo/', views.gasto_form, name='gasto_crear'),
    path('gastos/<int:pk>/', views.gasto_form, name='gasto_editar'),
    path('gastos/<int:pk>/eliminar/', views.gasto_eliminar, name='gasto_eliminar'),
    path('tipo-de-cambio/', views.tipos_cambio, name='tipos_cambio'),
    path('suscripciones/', views.suscripcion_lista, name='suscripcion_lista'),
    path('suscripciones/nueva/', views.suscripcion_form, name='suscripcion_crear'),
    path('suscripciones/<int:pk>/', views.suscripcion_form, name='suscripcion_editar'),
    path('suscripciones/<int:pk>/eliminar/', views.suscripcion_eliminar, name='suscripcion_eliminar'),
    path('suscripciones/<int:pk>/pagar/', views.suscripcion_pagar, name='suscripcion_pagar'),
]
