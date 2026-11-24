import api.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('incidencias', '0007_quitar_piso_puerta'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClaveIdempotencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('clave', models.CharField(max_length=100)),
                ('metodo', models.CharField(max_length=10)),
                ('ruta', models.CharField(max_length=255)),
                ('huella', models.CharField(max_length=64)),
                ('estado_http', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('respuesta', models.JSONField(blank=True, null=True)),
                ('creada', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='claves_idempotencia', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='claveidempotencia',
            constraint=models.UniqueConstraint(fields=('usuario', 'clave'), name='idempotencia_unica_por_usuario'),
        ),
        migrations.CreateModel(
            name='Adjunto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('archivo', models.FileField(upload_to=api.models.ruta_adjunto)),
                ('nombre_original', models.CharField(max_length=255)),
                ('tipo_contenido', models.CharField(max_length=100)),
                ('tamano', models.PositiveIntegerField()),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('incidencia', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='adjuntos', to='incidencias.incidencia')),
                ('subido_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['creado', 'id']},
        ),
    ]
