import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('incidencias', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Organizacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
            ],
            options={'verbose_name': 'organización', 'verbose_name_plural': 'organizaciones'},
        ),
        migrations.CreateModel(
            name='Edificio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('direccion', models.CharField(blank=True, max_length=200)),
                ('administradores', models.ManyToManyField(blank=True, related_name='edificios_administrados', to=settings.AUTH_USER_MODEL)),
                ('organizacion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='edificios', to='incidencias.organizacion')),
            ],
        ),
        migrations.AddConstraint(
            model_name='edificio',
            constraint=models.UniqueConstraint(fields=('organizacion', 'nombre'), name='edificio_unico_por_organizacion'),
        ),
        migrations.CreateModel(
            name='Unidad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identificador', models.CharField(max_length=20)),
                ('edificio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='unidades', to='incidencias.edificio')),
            ],
            options={'verbose_name': 'unidad', 'verbose_name_plural': 'unidades'},
        ),
        migrations.AddConstraint(
            model_name='unidad',
            constraint=models.UniqueConstraint(fields=('edificio', 'identificador'), name='unidad_unica_por_edificio'),
        ),
        migrations.CreateModel(
            name='Tecnico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('activo', models.BooleanField(default=True)),
                ('edificios', models.ManyToManyField(blank=True, related_name='tecnicos', to='incidencias.edificio')),
                ('usuario', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tecnico', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        # Los textos viejos se conservan con otro nombre hasta migrar los datos
        migrations.RenameField(model_name='perfil', old_name='edificio', new_name='edificio_texto'),
        migrations.AddField(
            model_name='perfil',
            name='edificio',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='residentes', to='incidencias.edificio', verbose_name='Edificio'),
        ),
        migrations.RenameField(model_name='incidencia', old_name='tecnico', new_name='tecnico_texto'),
        migrations.AddField(
            model_name='incidencia',
            name='tecnico',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='incidencias', to='incidencias.tecnico', verbose_name='Técnico asignado'),
        ),
        migrations.AddField(
            model_name='incidencia',
            name='edificio',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='incidencias', to='incidencias.edificio'),
        ),
        migrations.AddField(
            model_name='incidencia',
            name='unidad',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='incidencias', to='incidencias.unidad'),
        ),
        migrations.CreateModel(
            name='EventoIncidencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('creada', 'Creada'), ('estado_cambiado', 'Cambio de estado'), ('tecnico_asignado', 'Técnico asignado'), ('reabierta', 'Reabierta')], max_length=20)),
                ('estado_anterior', models.CharField(blank=True, max_length=15)),
                ('estado_nuevo', models.CharField(blank=True, max_length=15)),
                ('detalle', models.TextField(blank=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='eventos_incidencia', to=settings.AUTH_USER_MODEL)),
                ('incidencia', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='eventos', to='incidencias.incidencia')),
            ],
            options={'ordering': ['creado', 'id']},
        ),
    ]
