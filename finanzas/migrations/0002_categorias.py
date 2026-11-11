from django.db import migrations

CATEGORIAS = ['Hardware', 'Software', 'Licencias', 'Redes', 'Telecomunicaciones', 'Mantenimiento',
              'Servicios en la nube', 'Seguridad informática', 'Equipamiento', 'Otros']


def sembrar(apps, schema_editor):
    Categoria = apps.get_model('finanzas', 'CategoriaGasto')
    for nombre in CATEGORIAS:
        Categoria.objects.get_or_create(nombre=nombre)


class Migration(migrations.Migration):

    dependencies = [('finanzas', '0001_initial')]

    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
