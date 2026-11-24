from django.apps import AppConfig
from django.db.models.signals import post_migrate


def crear_grupos(sender, **kwargs):
    """Crea los grupos de roles después de aplicar las migraciones."""
    from django.contrib.auth.models import Group

    for nombre in ('Residente', 'Administrador'):
        Group.objects.get_or_create(name=nombre)


class IncidenciasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'incidencias'

    def ready(self):
        from . import signals  # noqa: F401  (registra las señales)
        post_migrate.connect(crear_grupos, sender=self)
