from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction, connection
from incidencias.models import Incidencia, Edificio, Organizacion

class Command(BaseCommand):
    help = 'Carga incidencias sintéticas para benchmark M3 (no usar en producción).'
    def add_arguments(self, parser):
        parser.add_argument('--cantidad', type=int, default=100000)
        parser.add_argument('--limpiar', action='store_true')
    def handle(self, *args, **opts):
        cantidad = max(1, opts['cantidad'])
        org, _ = Organizacion.objects.get_or_create(nombre='ORGANIZACION BENCHMARK M3')
        edificio, _ = Edificio.objects.get_or_create(organizacion=org, nombre='EDIFICIO BENCHMARK M3')
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.current_building', %s, false)", [str(edificio.pk)])
        user, _ = get_user_model().objects.get_or_create(username='benchmark_m3', defaults={'email':'benchmark@example.invalid'})
        if opts['limpiar']:
            Incidencia.objects.filter(edificio=edificio).delete()
        existentes = Incidencia.objects.filter(edificio=edificio).count()
        faltan = max(0, cantidad - existentes)
        estados = ['pendiente', 'en_proceso', 'resuelta', 'cerrada']
        prioridades = ['baja', 'media', 'alta']
        lote = []
        for i in range(faltan):
            lote.append(Incidencia(titulo=f'Incidencia benchmark {existentes+i:06d}', descripcion=f'Descripción sintética de prueba {existentes+i}', categoria='otros', prioridad=prioridades[i % 3], estado=estados[i % 4], residente=user, edificio=edificio))
            if len(lote) >= 2000:
                with transaction.atomic(): Incidencia.objects.bulk_create(lote, batch_size=2000)
                lote = []
        if lote:
            with transaction.atomic(): Incidencia.objects.bulk_create(lote, batch_size=2000)
        self.stdout.write(self.style.SUCCESS(f'Total en edificio benchmark: {Incidencia.objects.filter(edificio=edificio).count()}'))
