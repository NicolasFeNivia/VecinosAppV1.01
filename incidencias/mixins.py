from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect


def es_admin(user):
    """Administrador = superusuario o miembro del grupo 'Administrador'."""
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name='Administrador').exists())
    )


def tecnico_de(user):
    """Devuelve el Tecnico (reparador) activo ligado al usuario, o None."""
    if not (user and user.is_authenticated):
        return None
    tecnico = getattr(user, 'tecnico', None)
    return tecnico if tecnico is not None and tecnico.activo else None


def es_reparador(user):
    return tecnico_de(user) is not None and not es_admin(user)


class RedirigirSinPermisoMixin:
    """Si el usuario ya inició sesión pero no tiene permiso, lo manda a la lista con un aviso."""

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, 'No tienes permiso para realizar esta acción.')
            return redirect('incidencia_lista')
        return super().handle_no_permission()


class AdminRequiredMixin(RedirigirSinPermisoMixin, UserPassesTestMixin):
    def test_func(self):
        return es_admin(self.request.user)
