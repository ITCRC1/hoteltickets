from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', include('tickets.urls')),
]

# Personalizar títulos del admin
admin.site.site_header = 'Sistema de Tickets'
admin.site.site_title = 'Sistema de Tickets'
admin.site.index_title = 'Administración'
