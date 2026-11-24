import uuid

from django.conf import settings
from django.db import models

from incidencias.models import Incidencia

EXTENSIONES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif',
    'application/pdf': '.pdf',
}


class ClaveIdempotencia(models.Model):
    """Guarda la respuesta del primer POST con cierta Idempotency-Key para repetirla."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='claves_idempotencia'
    )
    clave = models.CharField(max_length=100)
    metodo = models.CharField(max_length=10)
    ruta = models.CharField(max_length=255)
    huella = models.CharField(max_length=64)
    estado_http = models.PositiveSmallIntegerField(null=True, blank=True)
    respuesta = models.JSONField(null=True, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['usuario', 'clave'], name='idempotencia_unica_por_usuario')
        ]


def ruta_adjunto(instance, filename):
    # El nombre lo decide el servidor según el contenido real, nunca el cliente.
    return f'adjuntos/{uuid.uuid4().hex}{EXTENSIONES.get(instance.tipo_contenido, ".bin")}'


class Adjunto(models.Model):
    incidencia = models.ForeignKey(Incidencia, on_delete=models.CASCADE, related_name='adjuntos')
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    archivo = models.FileField(upload_to=ruta_adjunto)
    nombre_original = models.CharField(max_length=255)
    tipo_contenido = models.CharField(max_length=100)
    tamano = models.PositiveIntegerField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado', 'id']

    def delete(self, *args, **kwargs):
        self.archivo.delete(save=False)
        super().delete(*args, **kwargs)
