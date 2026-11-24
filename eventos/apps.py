from django.apps import AppConfig


class EventosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'eventos'

    def ready(self):
        from django.db.models.signals import post_save

        from incidencias import signals as signals_mvp
        from incidencias.models import Incidencia

        # M5: el correo del MVP salía desde un post_save (se pierde si la transacción
        # se revierte y puede duplicarse). Lo reemplaza el patrón outbox de este módulo.
        post_save.disconnect(signals_mvp.avisar_incidencia_resuelta, sender=Incidencia)

        from . import celery_app  # noqa: F401  (deja configurado Celery en el proceso web)
        from . import signals  # noqa: F401
