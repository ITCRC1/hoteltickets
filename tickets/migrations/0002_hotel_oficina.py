from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotel',
            name='oficina',
            field=models.CharField(blank=True, max_length=100, verbose_name='Oficina'),
        ),
        migrations.AlterField(
            model_name='hotel',
            name='ubicacion',
            field=models.CharField(blank=True, max_length=200, verbose_name='Ubicación'),
        ),
    ]
