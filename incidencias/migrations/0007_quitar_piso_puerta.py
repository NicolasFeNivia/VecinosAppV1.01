from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('incidencias', '0006_datos_piso_y_unidad'),
    ]

    operations = [
        migrations.RemoveField(model_name='perfil', name='piso_puerta'),
    ]
