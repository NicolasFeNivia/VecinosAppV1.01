import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import eventos.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('incidencias', '0007_quitar_piso_puerta'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebhookEndpoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.URLField(max_length=500)),
                ('secreto', models.CharField(max_length=100)),
                ('eventos', models.JSONField(default=eventos.models.eventos_por_defecto)),
                ('activo', models.BooleanField(default=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('edificio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='webhooks', to='incidencias.edificio')),
            ],
            options={'ordering': ['id']},
        ),
        migrations.CreateModel(
            name='PreferenciaNotificacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('canal', models.CharField(max_length=20)),
                ('evento', models.CharField(max_length=50)),
                ('activo', models.BooleanField(default=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='preferencias_notificacion', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='preferencianotificacion',
            constraint=models.UniqueConstraint(fields=('usuario', 'canal', 'evento'), name='preferencia_unica'),
        ),
        migrations.CreateModel(
            name='Outbox',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(max_length=50)),
                ('canal', models.CharField(max_length=20)),
                ('destino', models.CharField(max_length=255)),
                ('payload', models.JSONField(default=dict)),
                ('clave_dedupe', models.CharField(max_length=200, unique=True)),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('enviando', 'Enviando'), ('entregado', 'Entregado'), ('fallido', 'Fallido')], default='pendiente', max_length=10)),
                ('intentos', models.PositiveIntegerField(default=0)),
                ('proximo_intento', models.DateTimeField(default=django.utils.timezone.now)),
                ('bloqueado_hasta', models.DateTimeField(blank=True, null=True)),
                ('ultimo_error', models.TextField(blank=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('entregado_en', models.DateTimeField(blank=True, null=True)),
                ('incidencia', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mensajes', to='incidencias.incidencia')),
            ],
            options={'ordering': ['id']},
        ),
        migrations.AddIndex(
            model_name='outbox',
            index=models.Index(fields=['estado', 'proximo_intento'], name='outbox_estado_proximo'),
        ),
    ]
