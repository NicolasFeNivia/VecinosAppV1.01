from django.contrib.auth import get_user_model
from django.test import TestCase

from . import dominio, services
from .models import (
    Edificio, EventoIncidencia, EventoInmutableError, Incidencia, Organizacion, Perfil, Tecnico,
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


class AislamientoEdificiosTest(TestCase):
    def setUp(self):
        from django.test import Client
        from django.contrib.auth.models import Group
        self.client = Client()
        org = Organizacion.objects.create(nombre='Organización multi')
        self.a = Edificio.objects.create(organizacion=org, nombre='Torre Norte')
        self.b = Edificio.objects.create(organizacion=org, nombre='Torre Sur')
        self.ana = User.objects.create_user('ana_norte', password='ClaveSegura123!')
        self.beto = User.objects.create_user('beto_sur', password='ClaveSegura123!')
        Perfil.objects.create(usuario=self.ana, edificio=self.a)
        Perfil.objects.create(usuario=self.beto, edificio=self.b)
        self.inc_b = services.crear_incidencia(residente=self.beto, edificio=self.b,
            titulo='Ascensor torre sur detenido', descripcion='No funciona', categoria='otros', prioridad='media')

    def test_residente_no_puede_consultar_incidencia_de_otro_edificio(self):
        self.client.login(username='ana_norte', password='ClaveSegura123!')
        respuesta = self.client.get(f'/incidencias/{self.inc_b.pk}/')
        self.assertEqual(respuesta.status_code, 404)

    def test_lista_no_incluye_incidencias_de_otro_edificio(self):
        self.client.login(username='ana_norte', password='ClaveSegura123!')
        respuesta = self.client.get('/incidencias/')
        self.assertNotContains(respuesta, self.inc_b.titulo)


class IntegridadM3Test(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre='Org integridad')
        edificio = Edificio.objects.create(organizacion=org, nombre='Edificio integridad')
        usuario = User.objects.create_user('integridad')
        self.incidencia = services.crear_incidencia(residente=usuario, edificio=edificio,
            titulo='Prueba de restricción', descripcion='Texto', categoria='otros', prioridad='media')

    def test_indices_m3_declarados_en_modelo(self):
        nombres = {indice.name for indice in Incidencia._meta.indexes}
        self.assertIn('inc_edif_estado_fecha', nombres)
        self.assertIn('inc_edif_prio_estado', nombres)
        self.assertIn('inc_tecnico_estado_fecha', nombres)


class MatrizPermisosM2Test(TestCase):
    def test_matriz_tiene_cuatro_roles_y_ocho_acciones(self):
        from .autorizacion import ACCIONES, MATRIZ_PERMISOS, ROLES
        self.assertEqual(len(ROLES), 4)
        self.assertEqual(len(ACCIONES), 8)
        self.assertEqual(set(MATRIZ_PERMISOS), set(ROLES))
        for rol in ROLES:
            with self.subTest(rol=rol):
                self.assertTrue(MATRIZ_PERMISOS[rol].issubset(set(ACCIONES)))

    def test_auditor_es_solo_lectura(self):
        from .autorizacion import MATRIZ_PERMISOS
        self.assertEqual(MATRIZ_PERMISOS['Auditor'], {'listar', 'ver_detalle'})
