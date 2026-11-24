from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from incidencias.models import EventoIncidencia

from . import servicios


@receiver(post_save, sender=EventoIncidencia)
def encolar_notificaciones(sender, instance, created, **kwargs):
    """Escribe el outbox en la misma transacción del caso de uso y despacha al confirmar."""
    if not created:
        return
    mensajes = servicios.mensajes_para_evento(instance)
    if mensajes:
        ids = [m.pk for m in mensajes]
        transaction.on_commit(partial(servicios.despachar_mensajes, ids))
