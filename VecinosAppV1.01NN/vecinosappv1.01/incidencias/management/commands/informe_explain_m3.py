from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count
from incidencias.models import Incidencia, Edificio

class Command(BaseCommand):
    help = 'Muestra EXPLAIN ANALYZE/BUFFERS de consultas típicas M3 (PostgreSQL).'
    def handle(self, *args, **opts):
        if connection.vendor != 'postgresql':
            self.stderr.write(self.style.ERROR('Este informe requiere PostgreSQL.'))
            return
        edificio = Edificio.objects.filter(nombre='EDIFICIO BENCHMARK M3').values_list('id', flat=True).first()
        if not edificio:
            self.stderr.write('No existe el edificio benchmark. Ejecuta cargar_incidencias_benchmark primero.')
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.current_building', %s, false)", [str(edificio)])
        if not Incidencia.objects.filter(edificio_id=edificio).exists():
            self.stderr.write('No hay incidencias en el edificio benchmark.')
            return
        consultas = {
            'listado': Incidencia.objects.filter(edificio_id=edificio, estado='pendiente').order_by('-creada')[:50],
            'busqueda': Incidencia.objects.filter(edificio_id=edificio, titulo__icontains='benchmark')[:50],
            'panel': Incidencia.objects.filter(edificio_id=edificio).order_by().values('estado').annotate(total=Count('id')),
        }
        for nombre, qs in consultas.items():
            self.stdout.write(f'\n--- {nombre.upper()} ---')
            self.stdout.write(qs.explain(analyze=True, buffers=True))
