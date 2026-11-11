from django.contrib import admin

from .models import CategoriaActivo, EstadoActivo


@admin.register(CategoriaActivo)
class CategoriaActivoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activa')
    list_filter = ('activa',)


@admin.register(EstadoActivo)
class EstadoActivoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'color', 'orden', 'activo')
    list_editable = ('orden', 'activo')
