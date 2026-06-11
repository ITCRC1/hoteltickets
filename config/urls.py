from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('tickets.urls')),
]

# Personalizar títulos del admin
admin.site.site_header = 'Sistema de Tickets'
admin.site.site_title = 'Sistema de Tickets'
admin.site.index_title = 'Administración'
