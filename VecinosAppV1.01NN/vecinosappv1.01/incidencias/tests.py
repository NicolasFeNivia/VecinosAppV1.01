from django.contrib.auth import get_user_model
from django.test import TestCase

from . import dominio, services
from .models import (
    Edificio, EventoIncidencia, EventoInmutableError, Incidencia, Organizacion, Tecnico,
)

User = get_user_model()
ESTADOS = [dominio.PENDIENTE, dominio.EN_PROCESO, dominio.RESUELTA, dominio.CERRADA]


class CasosDeUsoTest(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre='Org de prueba')
        self.edificio = Edificio.objects.create(organizacion=org, nombre='Torre A')
        self.otro_edificio = Edificio.objects.create(organizacion=org, nombre='Torre B')
        self.admin = User.objects.create_user('admin', password='x')
        self.residente = User.objects.create_user('ana', password='x')
        self.incidencia = services.crear_incidencia(
            residente=self.residente,
            edificio=self.edificio,
            titulo='Fuga de agua en el baño',
            descripcion='Gotea el techo',
            categoria='agua',
            prioridad='alta',
        )

    def _forzar_estado(self, estado):
        Incidencia.objects.filter(pk=self.incidencia.pk).update(estado=estado)
        self.incidencia.refresh_from_db()

    def test_crear_registra_evento(self):
        evento = self.incidencia.eventos.get()
        self.assertEqual(evento.tipo, EventoIncidencia.CREADA)
        self.assertEqual(evento.actor, self.residente)

    def test_transicion_valida_registra_evento(self):
        services.cambiar_estado(self.incidencia, dominio.EN_PROCESO, actor=self.admin)
        self.incidencia.refresh_from_db()
        self.assertEqual(self.incidencia.estado, dominio.EN_PROCESO)
        ultimo = self.incidencia.eventos.last()
        self.assertEqual(ultimo.tipo, EventoIncidencia.ESTADO_CAMBIADO)
        self.assertEqual((ultimo.estado_anterior, ultimo.estado_nuevo), ('pendiente', 'en_proceso'))

    def test_todas_las_transiciones_invalidas_son_rechazadas(self):
        for origen in ESTADOS:
            for destino in ESTADOS:
                if destino in dominio.TRANSICIONES[origen]:
                    continue
                with self.subTest(origen=origen, destino=destino):
                    self._forzar_estado(origen)
                    eventos_antes = self.incidencia.eventos.count()
                    with self.assertRaises(dominio.TransicionInvalida):
                        services.cambiar_estado(self.incidencia, destino, actor=self.admin)
                    self.incidencia.refresh_from_db()
                    self.assertEqual(self.incidencia.estado, origen)
                    self.assertEqual(self.incidencia.eventos.count(), eventos_antes)

    def test_reabrir_requiere_estado_reabrible_y_motivo(self):
        with self.assertRaises(dominio.TransicionInvalida):
            services.reabrir(self.incidencia, actor=self.admin, motivo='Volvió a gotear')
        self._forzar_estado(dominio.RESUELTA)
        with self.assertRaises(dominio.DominioError):
            services.reabrir(self.incidencia, actor=self.admin, motivo='   ')
        services.reabrir(self.incidencia, actor=self.admin, motivo='Volvió a gotear')
        self.incidencia.refresh_from_db()
        self.assertEqual(self.incidencia.estado, dominio.PENDIENTE)
        self.assertEqual(self.incidencia.eventos.last().tipo, EventoIncidencia.REABIERTA)

    def test_asignar_tecnico_valida_edificio_y_actividad(self):
        tecnico = Tecnico.objects.create(nombre='Luis')
        tecnico.edificios.add(self.otro_edificio)
        with self.assertRaises(dominio.AsignacionInvalida):
            services.asignar_tecnico(self.incidencia, tecnico, actor=self.admin)
        tecnico.edificios.add(self.edificio)
        services.asignar_tecnico(self.incidencia, tecnico, actor=self.admin)
        self.incidencia.refresh_from_db()
        self.assertEqual(self.incidencia.tecnico, tecnico)
        inactivo = Tecnico.objects.create(nombre='Inactivo', activo=False)
        inactivo.edificios.add(self.edificio)
        with self.assertRaises(dominio.AsignacionInvalida):
            services.asignar_tecnico(self.incidencia, inactivo, actor=self.admin)


class HistorialInmutableTest(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre='Org de prueba')
        edificio = Edificio.objects.create(organizacion=org, nombre='Torre A')
        residente = User.objects.create_user('ana', password='x')
        incidencia = services.crear_incidencia(
            residente=residente,
            edificio=edificio,
            titulo='Foco fundido en el pasillo',
            descripcion='Piso 3',
            categoria='electricidad',
            prioridad='media',
        )
        self.evento = incidencia.eventos.get()

    def test_no_se_puede_modificar(self):
        self.evento.detalle = 'cambiado'
        with self.assertRaises(EventoInmutableError):
            self.evento.save()

    def test_no_se_puede_borrar(self):
        with self.assertRaises(EventoInmutableError):
            self.evento.delete()

    def test_queryset_no_permite_update_ni_delete(self):
        with self.assertRaises(EventoInmutableError):
            EventoIncidencia.objects.all().update(detalle='x')
        with self.assertRaises(EventoInmutableError):
            EventoIncidencia.objects.all().delete()
