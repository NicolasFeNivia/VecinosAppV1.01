"""Casos de uso. Las vistas llaman aquí; aquí viven las reglas de negocio."""
from django.db import transaction

from . import dominio
from .models import EventoIncidencia, Incidencia


def _registrar(incidencia, tipo, actor, estado_anterior='', estado_nuevo='', detalle=''):
    return EventoIncidencia.objects.create(
        incidencia=incidencia,
        tipo=tipo,
        actor=actor,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        detalle=detalle,
    )


@transaction.atomic
def crear_incidencia(
    *, residente, edificio, titulo, descripcion, categoria, prioridad, foto=None, unidad=None
):
    incidencia = Incidencia.objects.create(
        residente=residente,
        edificio=edificio,
        unidad=unidad,
        titulo=titulo,
        descripcion=descripcion,
        categoria=categoria,
        prioridad=prioridad,
        foto=foto,
        estado=dominio.PENDIENTE,
    )
    _registrar(
        incidencia, EventoIncidencia.CREADA, residente, estado_nuevo=incidencia.estado
    )
    return incidencia


@transaction.atomic
def cambiar_estado(incidencia, nuevo_estado, *, actor):
    if not dominio.puede_pasar(incidencia.estado, nuevo_estado):
        raise dominio.TransicionInvalida(
            f'No se puede pasar de "{incidencia.estado}" a "{nuevo_estado}".'
        )
    anterior = incidencia.estado
    incidencia.estado = nuevo_estado
    incidencia.save(update_fields=['estado', 'actualizada'])
    _registrar(
        incidencia,
        EventoIncidencia.ESTADO_CAMBIADO,
        actor,
        estado_anterior=anterior,
        estado_nuevo=nuevo_estado,
    )
    return incidencia


@transaction.atomic
def asignar_tecnico(incidencia, tecnico, *, actor):
    """tecnico=None quita la asignación."""
    if incidencia.estado == dominio.CERRADA:
        raise dominio.AsignacionInvalida('No se puede asignar técnico a una incidencia cerrada.')
    if tecnico is not None:
        if not tecnico.activo:
            raise dominio.AsignacionInvalida('El técnico está inactivo.')
        if not tecnico.edificios.filter(pk=incidencia.edificio_id).exists():
            raise dominio.AsignacionInvalida('El técnico no pertenece al edificio de la incidencia.')
    if incidencia.tecnico_id == (tecnico.pk if tecnico else None):
        return incidencia
    incidencia.tecnico = tecnico
    incidencia.save(update_fields=['tecnico', 'actualizada'])
    _registrar(
        incidencia,
        EventoIncidencia.TECNICO_ASIGNADO,
        actor,
        detalle=tecnico.nombre if tecnico else 'Sin técnico',
    )
    return incidencia


@transaction.atomic
def reabrir(incidencia, *, actor, motivo):
    motivo = (motivo or '').strip()
    if not dominio.puede_reabrir(incidencia.estado):
        raise dominio.TransicionInvalida(
            'Solo se puede reabrir una incidencia resuelta o cerrada.'
        )
    if not motivo:
        raise dominio.DominioError('El motivo de la reapertura es obligatorio.')
    anterior = incidencia.estado
    incidencia.estado = dominio.DESTINO_REAPERTURA
    incidencia.save(update_fields=['estado', 'actualizada'])
    _registrar(
        incidencia,
        EventoIncidencia.REABIERTA,
        actor,
        estado_anterior=anterior,
        estado_nuevo=incidencia.estado,
        detalle=motivo,
    )
    return incidencia


@transaction.atomic
def gestionar(incidencia, *, actor, estado, prioridad, tecnico, notas_internas):
    """Lo que hace el administrador en la pantalla 'Gestionar'."""
    if estado != incidencia.estado:
        cambiar_estado(incidencia, estado, actor=actor)
    if tecnico != incidencia.tecnico:
        asignar_tecnico(incidencia, tecnico, actor=actor)
    incidencia.prioridad = prioridad
    incidencia.notas_internas = notas_internas
    incidencia.save(update_fields=['prioridad', 'notas_internas', 'actualizada'])
    return incidencia
