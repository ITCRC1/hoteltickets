"""
Comando para poblar la base con datos iniciales.
Uso: python manage.py seed
"""
from django.core.management.base import BaseCommand
from tickets.models import Hotel, Categoria


CATEGORIAS = [
    ('Mantenimiento general', '#fd7e14', 'Reparaciones, plomería, electricidad'),
    ('IT / Sistemas', '#0d6efd', 'Computadoras, red, internet, software'),
    ('Limpieza', '#20c997', 'Solicitudes y reportes de limpieza'),
    ('Lavandería', '#6f42c1', 'Ropa de cama, toallas, uniformes'),
    ('Aire acondicionado', '#0dcaf0', 'A/C, ventilación, climatización'),
    ('Seguridad', '#dc3545', 'Cerraduras, cámaras, accesos'),
    ('Servicio al huésped', '#198754', 'Solicitudes directas de huéspedes'),
    ('Suministros', '#ffc107', 'Faltantes de insumos y materiales'),
    ('Otros', '#6c757d', 'Lo que no encaja en otras categorías'),
]

HOTELES_DEMO = [
    'Hotel Vista Mar',
    'Hotel Centro',
    'Hotel Plaza',
]


class Command(BaseCommand):
    help = 'Carga categorías y hoteles de ejemplo'

    def handle(self, *args, **options):
        # Categorías
        for nombre, color, desc in CATEGORIAS:
            obj, creado = Categoria.objects.get_or_create(
                nombre=nombre,
                defaults={'color': color, 'descripcion': desc},
            )
            self.stdout.write(
                ('✔ Creada' if creado else '· Ya existe') + f' categoría: {obj.nombre}'
            )

        # Hoteles (opcional, solo si no hay ninguno)
        if not Hotel.objects.exists():
            for nombre in HOTELES_DEMO:
                Hotel.objects.create(nombre=nombre)
                self.stdout.write(f'✔ Creado hotel demo: {nombre}')
            self.stdout.write(self.style.WARNING(
                '(Hoteles de demostración creados. Edítalos o reemplázalos por los reales desde /admin)'
            ))

        self.stdout.write(self.style.SUCCESS('\nListo. Ya puedes empezar a usar el sistema.'))
