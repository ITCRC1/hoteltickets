from django.urls import path
from . import views

urlpatterns = [
    # Públicas
    path('', views.ticket_publico, name='ticket_publico'),
    path('confirmacion/<int:pk>/', views.ticket_confirmacion, name='ticket_confirmacion'),

    # Privadas
    path('dashboard/', views.dashboard, name='dashboard'),
    path('tickets/', views.ticket_lista, name='ticket_lista'),
    path('tickets/<int:pk>/', views.ticket_detalle, name='ticket_detalle'),
]
