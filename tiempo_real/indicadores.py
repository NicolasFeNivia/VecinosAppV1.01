"""4 indicadores operativos calculados con agregaciones en la base de datos."""
from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate
from django.utils.dateparse import parse_date

from incidencias import dominio
from incidencias.models import EventoIncidencia, Incidencia

SLA_HORAS = {'alta': 4, 'media': 24, 'baja': 72}  # mismos plazos que eventos/sla.py


def _fecha(valor):
    try:
        return parse_date(valor or '')
    except ValueError:
        return None


def filtros_desde(params):
    return {
        'edificio': params.get('edificio') or None,
        'tecnico': params.get('tecnico') or None,
        'desde': _fecha(params.get('desde')),
        'hasta': _fecha(params.get('hasta')),
    }


def _incidencias(f):
    qs = Incidencia.objects.all()
    if f['edificio']:
        qs = qs.filter(edificio_id=f['edificio'])
    if f['tecnico']:
        qs = qs.filter(tecnico_id=f['tecnico'])
    return qs


def _eventos(f, **extra):
    qs = EventoIncidencia.objects.filter(incidencia__in=_incidencias(f), **extra)
    if f['desde']:
        qs = qs.filter(creado__date__gte=f['desde'])
    if f['hasta']:
        qs = qs.filter(creado__date__lte=f['hasta'])
    return qs


def calcular(f):
    # Resoluciones: evento "pasó a resuelta"; duración = momento del evento - creación
    resoluciones = _eventos(f, tipo=EventoIncidencia.ESTADO_CAMBIADO, estado_nuevo=dominio.RESUELTA)
    resoluciones = resoluciones.annotate(
        duracion=ExpressionWrapper(F('creado') - F('incidencia__creada'), output_field=DurationField())
    )
    cumplidas = Q()
    for prioridad, horas in SLA_HORAS.items():
        cumplidas |= Q(incidencia__prioridad=prioridad, duracion__lte=timedelta(hours=horas))
    agregado = resoluciones.aggregate(
        total=Count('id'), promedio=Avg('duracion'), en_plazo=Count('id', filter=cumplidas)
    )
    total = agregado['total']
    promedio = agregado['promedio']

    reaperturas = _eventos(f, tipo=EventoIncidencia.REABIERTA).count()

    # Abiertos acumulados por día = creadas - resueltas/cerradas, acumulado
    creadas = dict(
        _incidencias(f).annotate(dia=TruncDate('creada')).values_list('dia').annotate(n=Count('id'))
    )
    terminadas = dict(
        _eventos(f, tipo=EventoIncidencia.ESTADO_CAMBIADO, estado_nuevo__in=[dominio.RESUELTA, dominio.CERRADA])
        .annotate(dia=TruncDate('creado')).values_list('dia').annotate(n=Count('id'))
    )
    acumulado, serie = 0, []
    for dia in sorted(set(creadas) | set(terminadas)):
        acumulado += creadas.get(dia, 0) - terminadas.get(dia, 0)
        serie.append({'dia': dia.isoformat(), 'abiertos': acumulado})

    abiertos_ahora = _incidencias(f).filter(
        estado__in=[dominio.PENDIENTE, dominio.EN_PROCESO]
    ).count()

    return {
        'tiempo_medio_resolucion_horas': round(promedio.total_seconds() / 3600, 2) if promedio else None,
        'cumplimiento_sla_pct': round(100 * agregado['en_plazo'] / total, 1) if total else None,
        'abiertos_acumulados': abiertos_ahora,
        'serie_abiertos': serie,
        'tasa_reapertura_pct': round(100 * reaperturas / total, 1) if total else None,
        'resueltas': total,
        'reaperturas': reaperturas,
    }
