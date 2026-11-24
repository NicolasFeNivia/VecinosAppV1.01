from django.core.management.base import BaseCommand, CommandError

from incidencias.models import Edificio, Organizacion, Unidad

ORG_POR_DEFECTO = 'Organización por defecto'
DEMO = ['Torre A', 'Torre B', 'Torre C']


class Command(BaseCommand):
    help = (
        'Crea edificios con sus pisos y apartamentos (101, 102, 103...). '
        'Se puede ejecutar varias veces: no duplica nada.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--edificio', help='Nombre del edificio a crear o completar.')
        parser.add_argument('--pisos', type=int, default=5, help='Cantidad de pisos (por defecto 5).')
        parser.add_argument(
            '--por-piso', type=int, default=3, help='Apartamentos por piso (por defecto 3).'
        )
        parser.add_argument(
            '--demo', action='store_true', help='Crea Torre A, Torre B y Torre C de ejemplo.'
        )

    def handle(self, *args, **opciones):
        if opciones['demo']:
            nombres = DEMO
        elif opciones['edificio']:
            nombres = [opciones['edificio'].strip()]
        else:
            raise CommandError('Indica --edificio "Nombre" o usa --demo.')

        pisos, por_piso = opciones['pisos'], opciones['por_piso']
        if pisos < 1 or por_piso < 1 or por_piso > 99:
            raise CommandError('--pisos debe ser >= 1 y --por-piso entre 1 y 99.')

        org, _ = Organizacion.objects.get_or_create(nombre=ORG_POR_DEFECTO)
        for nombre in nombres:
            edificio, _ = Edificio.objects.get_or_create(organizacion=org, nombre=nombre)
            nuevas = 0
            for piso in range(1, pisos + 1):
                for n in range(1, por_piso + 1):
                    _, creada = Unidad.objects.get_or_create(
                        edificio=edificio,
                        identificador=f'{piso}{n:02d}',
                        defaults={'piso': piso},
                    )
                    nuevas += creada
            self.stdout.write(self.style.SUCCESS(f'{nombre}: {nuevas} apartamentos nuevos.'))
