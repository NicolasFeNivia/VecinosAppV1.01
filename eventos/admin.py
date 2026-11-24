from django.contrib import admin

from .models import Outbox, PreferenciaNotificacion, WebhookEndpoint


@admin.register(Outbox)
class OutboxAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo', 'canal', 'destino', 'estado', 'intentos', 'proximo_intento')
    list_filter = ('estado', 'canal', 'tipo')


admin.site.register(WebhookEndpoint)
admin.site.register(PreferenciaNotificacion)
