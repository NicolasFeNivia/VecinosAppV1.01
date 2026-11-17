from django.db import migrations, models
import django.db.models.deletion


def instalar_rls(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE incidencias_incidencia ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE incidencias_incidencia FORCE ROW LEVEL SECURITY")
        cursor.execute("""CREATE POLICY incidencia_por_edificio ON incidencias_incidencia
            USING (edificio_id = NULLIF(current_setting('app.current_building', true), '')::bigint)
            WITH CHECK (edificio_id = NULLIF(current_setting('app.current_building', true), '')::bigint)""")
        cursor.execute("ALTER TABLE incidencias_comentario ENABLE ROW LEVEL SECURITY")
        cursor.execute("ALTER TABLE incidencias_comentario FORCE ROW LEVEL SECURITY")
        cursor.execute("""CREATE POLICY comentario_por_edificio ON incidencias_comentario
            USING (EXISTS (SELECT 1 FROM incidencias_incidencia i
                           WHERE i.id = incidencia_id AND i.edificio_id = NULLIF(current_setting('app.current_building', true), '')::bigint))
            WITH CHECK (EXISTS (SELECT 1 FROM incidencias_incidencia i
                           WHERE i.id = incidencia_id AND i.edificio_id = NULLIF(current_setting('app.current_building', true), '')::bigint))""")


def retirar_rls(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP POLICY IF EXISTS comentario_por_edificio ON incidencias_comentario')
        cursor.execute('ALTER TABLE incidencias_comentario NO FORCE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE incidencias_comentario DISABLE ROW LEVEL SECURITY')
        cursor.execute('DROP POLICY IF EXISTS incidencia_por_edificio ON incidencias_incidencia')
        cursor.execute('ALTER TABLE incidencias_incidencia NO FORCE ROW LEVEL SECURITY')
        cursor.execute('ALTER TABLE incidencias_incidencia DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [('incidencias', '0004_limpiar_campos_texto')]
    operations = [
        migrations.AddField(model_name='edificio', name='auditores', field=models.ManyToManyField(blank=True, related_name='edificios_auditados', to='auth.user')),
        migrations.AddIndex(model_name='incidencia', index=models.Index(fields=['edificio', 'estado', '-creada'], name='inc_edif_estado_fecha')),
        migrations.AddIndex(model_name='incidencia', index=models.Index(fields=['edificio', 'prioridad', 'estado'], name='inc_edif_prio_estado')),
        migrations.AddIndex(model_name='incidencia', index=models.Index(fields=['tecnico', 'estado', '-creada'], name='inc_tecnico_estado_fecha')),
        migrations.AddIndex(model_name='incidencia', index=models.Index(fields=['-creada'], name='inc_fecha_idx')),
        migrations.AddConstraint(model_name='incidencia', constraint=models.CheckConstraint(condition=~models.Q(titulo=''), name='inc_titulo_no_vacio')),
        migrations.AddConstraint(model_name='incidencia', constraint=models.CheckConstraint(condition=models.Q(prioridad__in=['baja', 'media', 'alta']), name='inc_prioridad_valida')),
        migrations.AddConstraint(model_name='incidencia', constraint=models.CheckConstraint(condition=models.Q(estado__in=['pendiente', 'en_proceso', 'resuelta', 'cerrada']), name='inc_estado_valido')),
        migrations.CreateModel(name='AuditoriaAcceso', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('ruta', models.CharField(max_length=500)), ('metodo', models.CharField(max_length=10)), ('resultado', models.PositiveSmallIntegerField(default=200)), ('direccion_ip', models.GenericIPAddressField(blank=True, null=True)), ('creado', models.DateTimeField(auto_now_add=True)), ('edificio', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='incidencias.edificio')), ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user'))], options={'ordering': ['-creado']}),
        migrations.AddIndex(model_name='auditoriaacceso', index=models.Index(fields=['edificio', '-creado'], name='audit_edif_fecha_idx')),
        migrations.RunPython(instalar_rls, retirar_rls),
    ]
