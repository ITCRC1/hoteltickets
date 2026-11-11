from django.apps import AppConfig


class FinanzasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finanzas'
    verbose_name = 'Finanzas'

    def ready(self):
        from core import papelera
        from .models import Gasto, Presupuesto, Suscripcion
        papelera.registrar(Presupuesto, etiqueta='Presupuestos', url_detalle='presupuesto_editar')
        papelera.registrar(Gasto, etiqueta='Gastos', url_detalle='gasto_editar')
        papelera.registrar(Suscripcion, etiqueta='Suscripciones', url_detalle='suscripcion_editar')
