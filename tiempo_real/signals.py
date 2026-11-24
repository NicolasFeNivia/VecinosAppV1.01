from functools import partial

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from incidencias.models import EventoIncidencia

from .consumers import grupo_edificio, grupo_incidencia


def _publicar(datos, incidencia_id, edificio_id):
    capa = get_channel_layer()
    if capa is None:
        return
    mensaje = {'type': 'incidencia.evento', 'datos': datos}
    try:
        send = async_to_sync(capa.group_send)
        send(grupo_incidencia(incidencia_id), mensaje)
        send(grupo_edificio(edificio_id), mensaje)
    except Exception:  # el tiempo real es un extra: nunca debe romper el cambio de estado
        pass


@receiver(post_save, sender=EventoIncidencia)
def avisar_en_vivo(sender, instance, created, **kwargs):
    if not created:
        return
    incidencia = instance.incidencia
    datos = {
        'incidencia_id': incidencia.pk,
        'titulo': incidencia.titulo,
        'evento': instance.tipo,
        'estado': incidencia.estado,
        'estado_display': incidencia.get_estado_display(),
        'badge': incidencia.estado_badge,
        'detalle': instance.detalle,
        'creado': instance.creado.isoformat(),
    }
    # Solo después de confirmar la transacción: nunca se anuncia algo que se revirtió
    transaction.on_commit(partial(_publicar, datos, incidencia.pk, incidencia.edificio_id))
