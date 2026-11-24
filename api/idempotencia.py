"""Idempotency-Key en POST: reintentar la misma petición no duplica el efecto."""
import hashlib
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .models import ClaveIdempotencia

ABANDONO = timedelta(seconds=60)


def _canonico(valor):
    if hasattr(valor, 'read'):
        return f'archivo:{valor.name}:{valor.size}'
    return valor


def _huella(request):
    datos = request.data
    if hasattr(datos, 'lists'):
        datos = {k: [_canonico(v) for v in vs] for k, vs in datos.lists()}
    cuerpo = json.dumps(datos, sort_keys=True, default=str)
    return hashlib.sha256(f'{request.method}|{request.path}|{cuerpo}'.encode()).hexdigest()


def _error(codigo, detalle, estado, **cabeceras):
    return Response({'codigo': codigo, 'detalle': detalle}, status=estado, headers=cabeceras)


def ejecutar_idempotente(request, ejecutar):
    """`ejecutar()` debe devolver una Response (las excepciones ya convertidas)."""
    clave = request.headers.get('Idempotency-Key')
    if clave is None:
        return ejecutar()
    if not clave.strip() or len(clave) > 100:
        return _error('idempotency_key_invalida', 'La clave debe tener entre 1 y 100 caracteres.', 400)

    huella = _huella(request)
    registro = None
    for _ in range(2):
        try:
            with transaction.atomic():
                registro = ClaveIdempotencia.objects.create(
                    usuario=request.user,
                    clave=clave,
                    metodo=request.method,
                    ruta=request.path,
                    huella=huella,
                )
            break
        except IntegrityError:
            existente = ClaveIdempotencia.objects.get(usuario=request.user, clave=clave)
            if existente.huella != huella:
                return _error(
                    'idempotency_key_reutilizada',
                    'Esa Idempotency-Key ya se usó con una petición distinta.',
                    422,
                )
            if existente.estado_http is not None:
                return Response(
                    existente.respuesta,
                    status=existente.estado_http,
                    headers={'Idempotent-Replayed': 'true'},
                )
            if timezone.now() - existente.creada > ABANDONO:
                existente.delete()  # el primer intento murió a medias: se permite reintentar
                continue
            return _error(
                'peticion_en_curso', 'La primera petición con esta clave aún se está procesando.',
                409, **{'Retry-After': '1'},
            )
    if registro is None:
        return _error('peticion_en_curso', 'Reintenta en unos segundos.', 409, **{'Retry-After': '1'})

    try:
        respuesta = ejecutar()
    except BaseException:
        registro.delete()
        raise

    if 200 <= respuesta.status_code < 300:
        registro.estado_http = respuesta.status_code
        registro.respuesta = json.loads(JSONRenderer().render(respuesta.data))
        registro.save(update_fields=['estado_http', 'respuesta'])
    else:
        registro.delete()  # los errores no se guardan: corregir y reintentar es legítimo
    return respuesta
