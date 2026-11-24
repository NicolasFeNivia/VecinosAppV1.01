"""Aplicación Celery.

Worker:  celery -A eventos.celery_app worker -l info
Beat:    celery -A eventos.celery_app beat -l info
"""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vecinosapp.settings')

app = Celery('vecinosapp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(['eventos'])

app.conf.beat_schedule = {
    # Red de seguridad: recoge mensajes pendientes (Redis caído, worker muerto a medias)
    'despachar-outbox': {
        'task': 'eventos.tasks.despachar_pendientes',
        'schedule': 30.0,
    },
    'escalar-fuera-de-sla': {
        'task': 'eventos.tasks.escalar_fuera_de_sla',
        'schedule': 15 * 60.0,
    },
}
