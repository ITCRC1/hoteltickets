from django.contrib import admin
from django.utils.html import format_html
from .models import Hotel, Categoria, Ticket, Comentario, RegistroAuditoria


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ubicacion', 'contacto_principal', 'telefono', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'ubicacion')


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'color_visual', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)

    def color_visual(self, obj):
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:4px">{}</span>',
            obj.color, obj.color
        )
    color_visual.short_description = 'Color'


class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 0
    readonly_fields = ('creado_en',)
    fields = ('autor', 'contenido', 'interno', 'creado_en')


class AuditoriaInline(admin.TabularInline):
    model = RegistroAuditoria
    extra = 0
    can_delete = False
    readonly_fields = ('usuario', 'usuario_nombre', 'accion', 'detalle', 'creado_en')
    fields = ('creado_en', 'usuario_nombre', 'accion', 'detalle')
    ordering = ('-creado_en',)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'titulo', 'hotel', 'categoria',
        'badge_prioridad', 'badge_estado',
        'solicitante_nombre', 'asignado_a', 'creado_en',
    )
    list_filter = ('estado', 'prioridad', 'hotel', 'categoria', 'asignado_a')
    search_fields = ('titulo', 'descripcion', 'solicitante_nombre', 'ubicacion_especifica')
    date_hierarchy = 'creado_en'
    readonly_fields = ('creado_en', 'actualizado_en', 'primera_respuesta_en', 'resuelto_en', 'cerrado_en')
    inlines = [ComentarioInline, AuditoriaInline]
    fieldsets = (
        ('Información', {
            'fields': ('titulo', 'descripcion', 'hotel', 'categoria', 'ubicacion_especifica')
        }),
        ('Solicitante', {
            'fields': ('solicitante_nombre', 'solicitante_usuario')
        }),
        ('Gestión', {
            'fields': ('prioridad', 'estado', 'asignado_a')
        }),
        ('Fechas', {
            'fields': ('creado_en', 'actualizado_en', 'primera_respuesta_en', 'resuelto_en', 'cerrado_en'),
            'classes': ('collapse',),
        }),
    )

    def badge_prioridad(self, obj):
        return format_html(
            '<span class="badge" style="background:#{}">{}</span>',
            {'baja': '6c757d', 'media': '0dcaf0', 'alta': 'fd7e14', 'urgente': 'dc3545'}.get(obj.prioridad, '6c757d'),
            obj.get_prioridad_display()
        )
    badge_prioridad.short_description = 'Prioridad'

    def badge_estado(self, obj):
        return format_html(
            '<span class="badge" style="background:#{};color:#fff;padding:3px 8px;border-radius:4px">{}</span>',
            {'abierto': '0d6efd', 'en_progreso': '0dcaf0', 'en_espera': 'ffc107',
             'resuelto': '198754', 'cerrado': '6c757d'}.get(obj.estado, '6c757d'),
            obj.get_estado_display()
        )
    badge_estado.short_description = 'Estado'


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('creado_en', 'ticket', 'usuario_nombre', 'accion', 'detalle_corto')
    list_filter = ('accion', 'creado_en')
    search_fields = ('ticket__titulo', 'usuario_nombre', 'detalle')
    date_hierarchy = 'creado_en'
    readonly_fields = ('ticket', 'usuario', 'usuario_nombre', 'accion', 'detalle', 'creado_en')

    def detalle_corto(self, obj):
        return obj.detalle[:60] + ('…' if len(obj.detalle) > 60 else '')
    detalle_corto.short_description = 'Detalle'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
