from django.db import migrations


def marcar_oficinas(apps, schema_editor):
    """Las oficinas (Drake, Sierpe, Uvita…) son puntos estratégicos fuera del hotel."""
    Hotel = apps.get_model('tickets', 'Hotel')
    Hotel.objects.filter(nombre__istartswith='Oficina').update(tipo='punto_externo')


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0007_alter_hotel_options_hotel_tipo'),
    ]

    operations = [migrations.RunPython(marcar_oficinas, migrations.RunPython.noop)]
