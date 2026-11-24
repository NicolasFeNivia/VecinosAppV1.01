from django.conf import settings
from django.db import models
from django.utils import timezone

from incidencias.models import Edificio, Incidencia


def eventos_por_defecto():
    return ['incidencia.resuelta']


class WebhookEndpoint(models.Model):
    """URL externa de un edificio que recibe eventos firmados con HMAC."""

    edificio = models.ForeignKey(Edificio, on_delete=models.CASCADE, related_name='webhooks')
    url = models.URLField(max_length=500)
    secreto = models.CharField(max_length=100)
    eventos = models.JSONField(default=eventos_por_defecto)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.edificio} -> {self.url}'


class PreferenciaNotificacion(models.Model):
    """Por defecto todo está activo; una fila con activo=False lo silencia."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='preferencias_notificacion'
    )
    canal = models.CharField(max_length=20)
    evento = models.CharField(max_length=50)
    activo = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'canal', 'evento'], name='preferencia_unica'
            )
        ]

    def __str__(self):
        return f'{self.usuario} {self.canal} {self.evento}: {self.activo}'


class Outbox(models.Model):
    """Un mensaje por entrega. Se escribe en la MISMA transacción que el cambio de estado."""

    PENDIENTE = 'pendiente'
    ENVIANDO = 'enviando'
    ENTREGADO = 'entregado'
    FALLIDO = 'fallido'  # cola de mensajes fallidos (dead letter)
    ESTADOS = [
        (PENDIENTE, 'Pendiente'),
        (ENVIANDO, 'Enviando'),
        (ENTREGADO, 'Entregado'),
        (FALLIDO, 'Fallido'),
    ]

    tipo = models.CharField(max_length=50)
    canal = models.CharField(max_length=20)
    destino = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    incidencia = models.ForeignKey(
        Incidencia, on_delete=models.CASCADE, null=True, blank=True, related_name='mensajes'
    )
    clave_dedupe = models.CharField(max_length=200, unique=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    intentos = models.PositiveIntegerField(default=0)
    proximo_intento = models.DateTimeField(default=timezone.now)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    ultimo_error = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    entregado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['estado', 'proximo_intento'], name='outbox_estado_proximo')]

    def __str__(self):
        return f'{self.tipo} -> {self.canal}:{self.destino} [{self.estado}]'
