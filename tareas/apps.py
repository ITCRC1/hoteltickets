from django.apps import AppConfig


class TareasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tareas'
    verbose_name = 'Tareas'

    def ready(self):
        from core import papelera
        from .models import Tarea
        papelera.registrar(Tarea, etiqueta='Tareas', url_detalle='tarea_editar')
