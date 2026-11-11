from django.contrib import admin

from .models import Auditoria, Directorio


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    """Solo consulta: la bitácora no se edita ni se borra."""
    list_display = ('creado_en', 'usuario_nombre', 'modulo', 'accion', 'objeto', 'ip')
    list_filter = ('modulo', 'accion')
    search_fields = ('usuario_nombre', 'objeto', 'detalle')
    date_hierarchy = 'creado_en'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Directorio)
class DirectorioAdmin(admin.ModelAdmin):
    """Correo de quien reporta → departamento (se usa al crear tickets desde el formulario público)."""
    list_display = ('email', 'nombre', 'departamento', 'actualizado_en')
    search_fields = ('email', 'nombre', 'departamento')
    list_filter = ('departamento',)
