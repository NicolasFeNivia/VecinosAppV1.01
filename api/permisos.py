from rest_framework.permissions import BasePermission

from incidencias.mixins import es_admin, tecnico_de


class SoloAdministrador(BasePermission):
    message = 'Solo el administrador puede hacer esto.'

    def has_permission(self, request, view):
        return es_admin(request.user)


def puede_cambiar_estado(user, incidencia):
    """Mismas reglas que la web: administrador, o el técnico asignado."""
    if es_admin(user):
        return True
    tecnico = tecnico_de(user)
    return tecnico is not None and incidencia.tecnico_id == tecnico.pk


def puede_adjuntar(user, incidencia):
    return puede_cambiar_estado(user, incidencia) or incidencia.residente_id == user.pk
