"""SLA por prioridad y escalamiento de incidencias vencidas."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from incidencias import dominio
from incidencias.models import Incidencia

from . import servicios
from .models import Outbox

SLA_HORAS = {'alta': 4, 'media': 24, 'baja': 72}
ESTADOS_ABIERTOS = [dominio.PENDIENTE, dominio.EN_PROCESO]


def incidencias_fuera_de_sla(ahora=None):
    ahora = ahora or timezone.now()
    condicion = Q()
    for prioridad, horas in SLA_HORAS.items():
        condicion |= Q(prioridad=prioridad, creada__lt=ahora - timedelta(hours=horas))
    return (
        Incidencia.objects.filter(estado__in=ESTADOS_ABIERTOS)
        .filter(condicion)
        .select_related('edificio', 'residente')
    )


def escalar_fuera_de_sla(ahora=None):
    """Avisa a los administradores del edificio y sube la prioridad a 'alta'.

    Se escala una sola vez por incidencia (la clave de deduplicación es sla:<id>),
    así que ejecutar la tarea varias veces no duplica avisos.
    """
    escaladas = []
    nuevos_ids = []
    for incidencia in incidencias_fuera_de_sla(ahora):
        with transaction.atomic():
            payload = servicios.payload_incidencia(incidencia)
            tipo = 'incidencia.sla_vencida'
            ya_existia = Outbox.objects.filter(
                clave_dedupe__startswith=f'sla:{incidencia.pk}:'
            ).exists()
            if ya_existia:
                continue
            mensajes = servicios._encolar_webhooks(incidencia, tipo, payload, f'sla:{incidencia.pk}')
            for admin in incidencia.edificio.administradores.exclude(email=''):
                if servicios.preferencia_activa(admin, 'correo', tipo):
                    mensajes.append(
                        servicios.encolar(
                            tipo=tipo,
                            canal='correo',
                            destino=admin.email,
                            payload={
                                'asunto': f'SLA vencido: "{incidencia.titulo}"',
                                'cuerpo': (
                                    f'La incidencia "{incidencia.titulo}" ({incidencia.prioridad}) '
                                    'superó su plazo de atención.\n\nVecinosApp'
                                ),
                                **payload,
                            },
                            clave=f'sla:{incidencia.pk}:{tipo}:correo:{admin.email}',
                            incidencia=incidencia,
                        )
                    )
            if incidencia.prioridad != 'alta':
                Incidencia.objects.filter(pk=incidencia.pk).update(prioridad='alta')
            escaladas.append(incidencia.pk)
            nuevos_ids += [m.pk for m in mensajes]
    if nuevos_ids:
        transaction.on_commit(lambda: servicios.despachar_mensajes(nuevos_ids))
    return escaladas
