"""Outbox: escribir mensajes en la transacción y entregarlos al menos una vez, sin duplicar."""
import logging
from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone

from incidencias import dominio
from incidencias.models import EventoIncidencia

from .canales import CANALES, ErrorPermanente
from .models import Outbox, PreferenciaNotificacion, WebhookEndpoint

logger = logging.getLogger(__name__)

MAX_INTENTOS = 6
LEASE_SEGUNDOS = 60          # si un worker muere, el mensaje se libera pasado este tiempo
BACKOFF_BASE_SEGUNDOS = 30
BACKOFF_MAX_SEGUNDOS = 3600

EVENTOS_VALIDOS = [
    'incidencia.creada',
    'incidencia.estado_cambiado',
    'incidencia.resuelta',
    'incidencia.tecnico_asignado',
    'incidencia.reabierta',
    'incidencia.sla_vencida',
]

_TIPO_BASE = {
    EventoIncidencia.CREADA: 'incidencia.creada',
    EventoIncidencia.ESTADO_CAMBIADO: 'incidencia.estado_cambiado',
    EventoIncidencia.TECNICO_ASIGNADO: 'incidencia.tecnico_asignado',
    EventoIncidencia.REABIERTA: 'incidencia.reabierta',
}


def espera_backoff(intentos):
    """Espera exponencial: 30 s, 60 s, 120 s ... hasta 1 h."""
    return min(BACKOFF_BASE_SEGUNDOS * 2 ** max(intentos - 1, 0), BACKOFF_MAX_SEGUNDOS)


# ---------- Escritura (dentro de la transacción del cambio) ----------

def encolar(*, tipo, canal, destino, payload, clave, incidencia=None):
    """Idempotente: la misma clave nunca crea dos mensajes."""
    mensaje, _ = Outbox.objects.get_or_create(
        clave_dedupe=clave,
        defaults={
            'tipo': tipo,
            'canal': canal,
            'destino': str(destino),
            'payload': payload,
            'incidencia': incidencia,
        },
    )
    return mensaje


def preferencia_activa(usuario, canal, tipo):
    fila = PreferenciaNotificacion.objects.filter(
        usuario=usuario, canal=canal, evento=tipo
    ).first()
    return True if fila is None else fila.activo


def payload_incidencia(incidencia, evento=None):
    datos = {
        'incidencia': {
            'id': incidencia.pk,
            'titulo': incidencia.titulo,
            'estado': incidencia.estado,
            'prioridad': incidencia.prioridad,
            'categoria': incidencia.categoria,
            'edificio_id': incidencia.edificio_id,
            'residente': incidencia.residente.username,
            'tecnico_id': incidencia.tecnico_id,
        }
    }
    if evento is not None:
        datos['evento'] = {
            'tipo': evento.tipo,
            'estado_anterior': evento.estado_anterior,
            'estado_nuevo': evento.estado_nuevo,
            'actor': evento.actor.username if evento.actor_id else None,
            'detalle': evento.detalle,
        }
    return datos


def _encolar_webhooks(incidencia, tipo, payload, prefijo_clave):
    mensajes = []
    for endpoint in WebhookEndpoint.objects.filter(edificio_id=incidencia.edificio_id, activo=True):
        if tipo in (endpoint.eventos or []):
            mensajes.append(
                encolar(
                    tipo=tipo,
                    canal='webhook',
                    destino=endpoint.pk,
                    payload=payload,
                    clave=f'{prefijo_clave}:{tipo}:webhook:{endpoint.pk}',
                    incidencia=incidencia,
                )
            )
    return mensajes


def mensajes_para_evento(evento):
    """Crea (en la transacción actual) los mensajes que provoca un EventoIncidencia."""
    incidencia = evento.incidencia
    tipos = [_TIPO_BASE[evento.tipo]] if evento.tipo in _TIPO_BASE else []
    if evento.tipo == EventoIncidencia.ESTADO_CAMBIADO and evento.estado_nuevo == dominio.RESUELTA:
        tipos.append('incidencia.resuelta')

    mensajes = []
    payload = payload_incidencia(incidencia, evento)
    for tipo in tipos:
        mensajes += _encolar_webhooks(incidencia, tipo, payload, f'evento:{evento.pk}')
        if tipo == 'incidencia.resuelta':
            residente = incidencia.residente
            if residente.email and preferencia_activa(residente, 'correo', tipo):
                mensajes.append(
                    encolar(
                        tipo=tipo,
                        canal='correo',
                        destino=residente.email,
                        payload={
                            'asunto': f'Tu incidencia "{incidencia.titulo}" fue resuelta',
                            'cuerpo': (
                                f'Hola {residente.username},\n\n'
                                f'Tu incidencia "{incidencia.titulo}" cambió su estado a Resuelta.\n'
                                'Si todo está bien, no necesitas hacer nada más.\n\n'
                                'VecinosApp'
                            ),
                            **payload,
                        },
                        clave=f'evento:{evento.pk}:{tipo}:correo:{residente.email}',
                        incidencia=incidencia,
                    )
                )
    return mensajes


# ---------- Entrega ----------

def despachar_mensajes(ids):
    """Se llama con transaction.on_commit: publica en Celery. Si falla, beat lo recoge."""
    from .tasks import entregar_mensaje

    for pk in ids:
        try:
            entregar_mensaje.delay(pk)
        except Exception:  # Redis caído: el mensaje sigue seguro en la tabla
            logger.warning('No se pudo publicar el mensaje %s en Celery; lo recogerá beat.', pk)


def pendientes_vencidos(ahora=None, lote=100):
    """IDs listos para entregar: pendientes cuyo turno llegó o con 'lease' vencido."""
    ahora = ahora or timezone.now()
    return list(
        Outbox.objects.filter(
            Q(estado=Outbox.PENDIENTE, proximo_intento__lte=ahora)
            | Q(estado=Outbox.ENVIANDO, bloqueado_hasta__lt=ahora)
        )
        .order_by('id')
        .values_list('pk', flat=True)[:lote]
    )


def entregar(pk, *, ahora=None):
    """Entrega un mensaje. Devuelve 'entregado', 'reintento', 'fallido' u 'omitido'.

    El 'claim' es un UPDATE condicional atómico: solo un worker puede reclamar el
    mensaje a la vez. Si el worker muere después de reclamar, el lease vence y otro
    worker lo retoma (entrega al menos una vez; los webhooks llevan X-Vecinos-Delivery
    para que el receptor deduplique).
    """
    ahora = ahora or timezone.now()
    reclamados = (
        Outbox.objects.filter(pk=pk)
        .filter(
            Q(estado=Outbox.PENDIENTE, proximo_intento__lte=ahora)
            | Q(estado=Outbox.ENVIANDO, bloqueado_hasta__lt=ahora)
        )
        .update(
            estado=Outbox.ENVIANDO,
            bloqueado_hasta=ahora + timedelta(seconds=LEASE_SEGUNDOS),
            intentos=F('intentos') + 1,
        )
    )
    if not reclamados:
        return 'omitido'

    mensaje = Outbox.objects.get(pk=pk)
    if mensaje.intentos > MAX_INTENTOS:
        Outbox.objects.filter(pk=pk).update(
            estado=Outbox.FALLIDO, bloqueado_hasta=None, ultimo_error='Superó el máximo de intentos.'
        )
        return 'fallido'

    try:
        CANALES[mensaje.canal].enviar(mensaje)
    except ErrorPermanente as error:
        Outbox.objects.filter(pk=pk).update(
            estado=Outbox.FALLIDO, bloqueado_hasta=None, ultimo_error=str(error)[:1000]
        )
        return 'fallido'
    except Exception as error:
        if mensaje.intentos >= MAX_INTENTOS:
            Outbox.objects.filter(pk=pk).update(
                estado=Outbox.FALLIDO, bloqueado_hasta=None, ultimo_error=str(error)[:1000]
            )
            return 'fallido'
        Outbox.objects.filter(pk=pk).update(
            estado=Outbox.PENDIENTE,
            bloqueado_hasta=None,
            proximo_intento=ahora + timedelta(seconds=espera_backoff(mensaje.intentos)),
            ultimo_error=str(error)[:1000],
        )
        return 'reintento'

    Outbox.objects.filter(pk=pk, estado=Outbox.ENVIANDO).update(
        estado=Outbox.ENTREGADO, entregado_en=timezone.now(), bloqueado_hasta=None, ultimo_error=''
    )
    return 'entregado'
