from django.contrib import admin

from .models import Auditoria


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
