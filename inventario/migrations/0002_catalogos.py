from django.db import migrations

CATEGORIAS = ['Computadoras', 'Laptops', 'Tablets', 'Impresoras', 'Routers', 'Switches', 'Puntos de acceso',
              'Servidores', 'Cámaras', 'UPS', 'Periféricos', 'Otros']
ESTADOS = [('En uso', 'success', 1), ('En bodega', 'info', 2), ('En reparación', 'warning', 3),
           ('Dañado', 'danger', 4), ('Dado de baja', 'secondary', 5)]


def sembrar(apps, schema_editor):
    Categoria = apps.get_model('inventario', 'CategoriaActivo')
    Estado = apps.get_model('inventario', 'EstadoActivo')
    for nombre in CATEGORIAS:
        Categoria.objects.get_or_create(nombre=nombre)
    for nombre, color, orden in ESTADOS:
        Estado.objects.get_or_create(nombre=nombre, defaults={'color': color, 'orden': orden})


class Migration(migrations.Migration):

    dependencies = [('inventario', '0001_initial')]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
