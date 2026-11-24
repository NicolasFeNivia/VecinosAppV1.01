import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('incidencias', '0004_limpiar_campos_texto'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='unidad',
            options={
                'ordering': ['edificio', 'piso', 'identificador'],
                'verbose_name': 'unidad',
                'verbose_name_plural': 'unidades',
            },
        ),
        migrations.AddField(
            model_name='unidad',
            name='piso',
            field=models.PositiveSmallIntegerField(default=1, verbose_name='Piso'),
        ),
        migrations.AlterField(
            model_name='unidad',
            name='identificador',
            field=models.CharField(max_length=20, verbose_name='Apartamento'),
        ),
        migrations.AddField(
            model_name='perfil',
            name='unidad',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='residentes',
                to='incidencias.unidad',
                verbose_name='Apartamento',
            ),
        ),
    ]
