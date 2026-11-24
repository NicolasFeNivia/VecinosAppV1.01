from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

from incidencias import dominio


class PrecondicionFallida(APIException):
    status_code = status.HTTP_412_PRECONDITION_FAILED
    default_detail = 'El recurso cambió desde que lo leíste (If-Match no coincide).'
    default_code = 'precondicion_fallida'


_CODIGOS = {
    dominio.TransicionInvalida: 'transicion_invalida',
    dominio.AsignacionInvalida: 'asignacion_invalida',
    dominio.DominioError: 'regla_de_negocio',
}


def manejador(exc, context):
    """Las reglas de negocio rechazadas salen como 422 con un código estable."""
    if isinstance(exc, dominio.DominioError):
        codigo = next(c for tipo, c in _CODIGOS.items() if isinstance(exc, tipo))
        return Response({'codigo': codigo, 'detalle': str(exc)}, status=422)
    return exception_handler(exc, context)
