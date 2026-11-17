from django.db import migrations
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models


def instalar_trigramas(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
            cursor.execute("CREATE INDEX IF NOT EXISTS inc_titulo_trgm_idx ON incidencias_incidencia USING gin (titulo gin_trgm_ops)")
            cursor.execute("CREATE INDEX IF NOT EXISTS inc_descripcion_trgm_idx ON incidencias_incidencia USING gin (descripcion gin_trgm_ops)")
            cursor.execute("CREATE INDEX IF NOT EXISTS inc_abiertas_edif_idx ON incidencias_incidencia (edificio_id, prioridad, creada DESC) WHERE estado IN ('pendiente', 'en_proceso')")

def retirar_trigramas(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('DROP INDEX IF EXISTS inc_abiertas_edif_idx')
            cursor.execute('DROP INDEX IF EXISTS inc_descripcion_trgm_idx')
            cursor.execute('DROP INDEX IF EXISTS inc_titulo_trgm_idx')

class Migration(migrations.Migration):
    dependencies = [('incidencias', '0005_m2_multiedificio_m3_postgres')]
    operations = [migrations.RunPython(instalar_trigramas, retirar_trigramas)]
