from celery import shared_task

from . import servicios, sla


@shared_task(acks_late=True, reject_on_worker_lost=True)
def entregar_mensaje(pk):
    return servicios.entregar(pk)


@shared_task
def despachar_pendientes():
    ids = servicios.pendientes_vencidos()
    for pk in ids:
        entregar_mensaje.delay(pk)
    return len(ids)


@shared_task
def escalar_fuera_de_sla():
    return sla.escalar_fuera_de_sla()
