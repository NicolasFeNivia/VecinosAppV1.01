import hashlib

from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .excepciones import PrecondicionFallida


def calcular_etag(datos):
    cuerpo = JSONRenderer().render(datos)
    return '"%s"' % hashlib.sha256(cuerpo).hexdigest()[:32]


def _etags(cabecera):
    return [e.strip().removeprefix('W/') for e in cabecera.split(',') if e.strip()]


def coincide(cabecera, etag):
    etags = _etags(cabecera)
    return '*' in etags or etag in etags


def respuesta_con_etag(request, datos):
    """GET condicional: 304 si el cliente ya tiene esta versión (If-None-Match)."""
    etag = calcular_etag(datos)
    cabeceras = {'ETag': etag, 'Cache-Control': 'private, must-revalidate'}
    if coincide(request.headers.get('If-None-Match', ''), etag):
        return Response(status=304, headers=cabeceras)
    return Response(datos, headers=cabeceras)


def exigir_if_match(request, datos_actuales):
    """Escritura condicional: si el cliente manda If-Match y ya cambió, 412."""
    cabecera = request.headers.get('If-Match')
    if cabecera and not coincide(cabecera, calcular_etag(datos_actuales)):
        raise PrecondicionFallida()
