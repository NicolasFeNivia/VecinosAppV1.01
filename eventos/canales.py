"""Canales de notificación detrás de una misma interfaz: enviar(mensaje)."""
import json
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import send_mail

from . import firma


class ErrorPermanente(Exception):
    """Reintentar no sirve (p. ej. el endpoint ya no existe): va directo a fallidos."""


class Canal:
    nombre = ''

    def enviar(self, mensaje):
        raise NotImplementedError


class CanalCorreo(Canal):
    nombre = 'correo'

    def enviar(self, mensaje):
        send_mail(
            subject=mensaje.payload['asunto'],
            message=mensaje.payload['cuerpo'],
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[mensaje.destino],
            fail_silently=False,
        )


class CanalWebhook(Canal):
    nombre = 'webhook'
    TIMEOUT = 10

    def enviar(self, mensaje):
        from .models import WebhookEndpoint

        endpoint = WebhookEndpoint.objects.filter(pk=int(mensaje.destino), activo=True).first()
        if endpoint is None:
            raise ErrorPermanente('El endpoint del webhook no existe o está inactivo.')
        cuerpo = json.dumps(
            {
                'id': mensaje.pk,
                'tipo': mensaje.tipo,
                'creado': mensaje.creado.isoformat(),
                'datos': mensaje.payload,
            },
            sort_keys=True,
        ).encode()
        peticion = Request(
            endpoint.url,
            data=cuerpo,
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'X-Vecinos-Event': mensaje.tipo,
                # El receptor deduplica con este id si recibe un reintento
                'X-Vecinos-Delivery': str(mensaje.pk),
                'X-Vecinos-Signature': firma.firmar(endpoint.secreto, cuerpo),
            },
        )
        with urlopen(peticion, timeout=self.TIMEOUT) as respuesta:  # noqa: S310
            if not 200 <= respuesta.status < 300:
                raise RuntimeError(f'El webhook respondió {respuesta.status}')


CANALES = {'correo': CanalCorreo(), 'webhook': CanalWebhook()}
