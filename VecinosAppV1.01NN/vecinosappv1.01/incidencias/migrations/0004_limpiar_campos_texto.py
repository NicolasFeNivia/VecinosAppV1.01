import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('incidencias', '0003_datos_texto_a_entidades'),
    ]

    operations = [
        migrations.RemoveField(model_name='perfil', name='edificio_texto'),
        migrations.RemoveField(model_name='incidencia', name='tecnico_texto'),
        migrations.AlterField(
            model_name='incidencia',
            name='edificio',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='incidencias', to='incidencias.edificio'),
        ),
    ]
