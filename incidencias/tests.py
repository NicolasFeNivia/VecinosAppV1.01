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


# ---------- Registro con edificio / piso / apartamento y visibilidad por rol ----------

from django.urls import reverse  # noqa: E402

from .forms import RegistroForm  # noqa: E402
from .models import Perfil, Unidad  # noqa: E402
from .views import incidencias_visibles  # noqa: E402


def _crear_edificio(org, nombre, pisos=2, por_piso=3):
    edificio = Edificio.objects.create(organizacion=org, nombre=nombre)
    for piso in range(1, pisos + 1):
        for n in range(1, por_piso + 1):
            Unidad.objects.create(edificio=edificio, piso=piso, identificador=f'{piso}{n:02d}')
    return edificio


class RegistroViviendaTest(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre='Org')
        self.torre_a = _crear_edificio(org, 'Torre A')
        self.torre_b = _crear_edificio(org, 'Torre B')
        Edificio.objects.create(organizacion=org, nombre='Sin apartamentos')

    def _datos(self, **extra):
        datos = {
            'username': 'nuevo',
            'email': 'nuevo@ejemplo.com',
            'nombre_completo': 'Nuevo Usuario',
            'password1': 'Clave-segura-9876',
            'password2': 'Clave-segura-9876',
            'edificio': self.torre_a.pk,
            'piso': 1,
            'unidad': Unidad.objects.get(edificio=self.torre_a, identificador='102').pk,
        }
        datos.update(extra)
        return datos

    def test_registro_valido_guarda_edificio_y_apartamento(self):
        form = RegistroForm(self._datos())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        perfil = Perfil.objects.get(usuario=user)
        self.assertEqual(perfil.edificio, self.torre_a)
        self.assertEqual((perfil.unidad.piso, perfil.unidad.identificador), (1, '102'))

    def test_el_selector_solo_ofrece_edificios_con_apartamentos(self):
        nombres = [e['nombre'] for e in RegistroForm().datos_vivienda]
        self.assertEqual(nombres, ['Torre A', 'Torre B'])

    def test_etiqueta_del_piso_lista_los_apartamentos(self):
        torre_a = RegistroForm().datos_vivienda[0]
        self.assertEqual(torre_a['pisos'][0]['etiqueta'], 'Piso 1: 101, 102, 103')

    def test_todo_es_obligatorio(self):
        for campo in ('edificio', 'piso', 'unidad'):
            with self.subTest(campo=campo):
                datos = self._datos()
                datos.pop(campo)
                form = RegistroForm(datos)
                self.assertFalse(form.is_valid())
                self.assertIn(campo, form.errors)

    def test_apartamento_de_otro_edificio_es_rechazado(self):
        apto_b = Unidad.objects.get(edificio=self.torre_b, identificador='102')
        form = RegistroForm(self._datos(unidad=apto_b.pk))
        self.assertFalse(form.is_valid())
        self.assertIn('unidad', form.errors)

    def test_apartamento_de_otro_piso_es_rechazado(self):
        form = RegistroForm(self._datos(piso=2))
        self.assertFalse(form.is_valid())
        self.assertIn('unidad', form.errors)

    def test_registro_por_la_pagina(self):
        respuesta = self.client.post(reverse('registro'), self._datos())
        self.assertRedirects(respuesta, reverse('login'))
        self.assertEqual(Perfil.objects.get(usuario__username='nuevo').edificio, self.torre_a)

    def test_perfil_siempre_queda_con_el_edificio_de_su_apartamento(self):
        user = User.objects.create_user('lola', password='x')
        perfil = user.perfil
        perfil.edificio = self.torre_a
        perfil.unidad = Unidad.objects.get(edificio=self.torre_b, identificador='101')
        perfil.save()
        perfil.refresh_from_db()
        self.assertEqual(perfil.edificio, self.torre_b)

    def test_el_residente_no_puede_cambiar_su_edificio_desde_el_perfil(self):
        user = User.objects.create_user('lola', password='x')
        user.perfil.unidad = Unidad.objects.get(edificio=self.torre_a, identificador='101')
        user.perfil.save()
        self.client.force_login(user)
        self.client.post(
            reverse('perfil'),
            {'nombre_completo': 'Lola', 'edificio': self.torre_b.pk},
        )
        user.perfil.refresh_from_db()
        self.assertEqual(user.perfil.edificio, self.torre_a)
        self.assertEqual(user.perfil.nombre_completo, 'Lola')


class BaseRolesTest(TestCase):
    """Datos compartidos: 3 edificios, residentes, administrador y un reparador."""

    def setUp(self):
        org = Organizacion.objects.create(nombre='Org')
        self.torre_a = _crear_edificio(org, 'Torre A', pisos=1)
        self.torre_b = _crear_edificio(org, 'Torre B', pisos=1)
        self.torre_c = _crear_edificio(org, 'Torre C', pisos=1)

        self.admin = User.objects.create_superuser('root', password='x')
        self.ana = self._residente('ana', self.torre_a)
        self.beto = self._residente('beto', self.torre_a)
        self.carla = self._residente('carla', self.torre_b)
        self.sin_edificio = User.objects.create_user('sinedificio', password='x')

        self.reparador_user = User.objects.create_user('luis', password='x')
        self.tecnico = Tecnico.objects.create(nombre='Luis', usuario=self.reparador_user)
        self.tecnico.edificios.add(self.torre_a)

        self.i_ana = self._incidencia(self.ana, self.torre_a)
        self.i_beto = self._incidencia(self.beto, self.torre_a)
        self.i_carla = self._incidencia(self.carla, self.torre_b)
        # Torre C: pendiente, no es de ninguno de los edificios del reparador
        self.i_c = self._incidencia(self._residente('dani', self.torre_c), self.torre_c)

    def _residente(self, nombre, edificio):
        user = User.objects.create_user(nombre, password='x')
        user.perfil.unidad = edificio.unidades.first()
        user.perfil.save()
        return user

    def _incidencia(self, residente, edificio):
        return services.crear_incidencia(
            residente=residente,
            edificio=edificio,
            unidad=residente.perfil.unidad,
            titulo='Fuga de agua en el pasillo',
            descripcion='Descripción',
            categoria='agua',
            prioridad='media',
        )

    def _ids(self, user):
        return set(incidencias_visibles(user).values_list('pk', flat=True))


class VisibilidadPorRolTest(BaseRolesTest):
    def test_administrador_ve_todas_las_de_todos_los_edificios(self):
        self.assertEqual(
            self._ids(self.admin),
            {self.i_ana.pk, self.i_beto.pk, self.i_carla.pk, self.i_c.pk},
        )

    def test_residente_ve_las_de_su_edificio_y_no_las_de_otros(self):
        # Ana y Beto son vecinos (Torre A): se ven entre sí; Carla (Torre B) no
        self.assertEqual(self._ids(self.ana), {self.i_ana.pk, self.i_beto.pk})
        self.assertEqual(self._ids(self.beto), {self.i_ana.pk, self.i_beto.pk})
        self.assertEqual(self._ids(self.carla), {self.i_carla.pk})

    def test_residente_sin_edificio_no_ve_nada(self):
        self.assertEqual(self._ids(self.sin_edificio), set())

    def test_reparador_sin_asignaciones_no_ve_nada(self):
        self.assertEqual(self._ids(self.reparador_user), set())

    def test_reparador_ve_solo_las_asignadas(self):
        services.asignar_tecnico(self.i_ana, self.tecnico, actor=self.admin)
        self.assertEqual(self._ids(self.reparador_user), {self.i_ana.pk})
        services.cambiar_estado(self.i_ana, dominio.EN_PROCESO, actor=self.admin)
        self.assertEqual(self._ids(self.reparador_user), {self.i_ana.pk})

    def test_tecnico_inactivo_pierde_la_vista_de_reparador(self):
        services.asignar_tecnico(self.i_ana, self.tecnico, actor=self.admin)
        Tecnico.objects.filter(pk=self.tecnico.pk).update(activo=False)
        self.reparador_user = User.objects.get(pk=self.reparador_user.pk)
        self.assertEqual(self._ids(self.reparador_user), set())

    def test_detalle_de_otro_edificio_da_404(self):
        self.client.force_login(self.ana)
        self.assertEqual(
            self.client.get(reverse('incidencia_detalle', args=[self.i_carla.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse('incidencia_detalle', args=[self.i_beto.pk])).status_code, 200
        )

    def test_la_lista_respeta_el_rol(self):
        self.client.force_login(self.ana)
        lista = self.client.get(reverse('incidencia_lista')).context['object_list']
        self.assertEqual({i.pk for i in lista}, {self.i_ana.pk, self.i_beto.pk})
        self.client.force_login(self.admin)
        lista = self.client.get(reverse('incidencia_lista')).context['object_list']
        self.assertEqual(len(lista), 4)

    def test_nueva_incidencia_guarda_el_apartamento_del_residente(self):
        self.client.force_login(self.ana)
        self.client.post(reverse('incidencia_crear'), {
            'titulo': 'Ascensor dañado hace dos días',
            'descripcion': 'No funciona',
            'categoria': 'otros',
            'prioridad': 'media',
        })
        nueva = Incidencia.objects.get(titulo='Ascensor dañado hace dos días')
        self.assertEqual(nueva.edificio, self.torre_a)
        self.assertEqual(nueva.unidad, self.ana.perfil.unidad)


class HistorialYEstadoPorRolTest(BaseRolesTest):
    """Historial: solo creador y administrador. Estado: el reparador asignado."""

    def setUp(self):
        super().setUp()
        services.asignar_tecnico(self.i_ana, self.tecnico, actor=self.admin)
        self.url_detalle = reverse('incidencia_detalle', args=[self.i_ana.pk])
        self.url_estado = reverse('incidencia_estado', args=[self.i_ana.pk])

    def _estado(self):
        self.i_ana.refresh_from_db()
        return self.i_ana.estado

    def test_historial_lo_ven_el_creador_y_el_administrador(self):
        for usuario in (self.ana, self.admin):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                respuesta = self.client.get(self.url_detalle)
                self.assertTrue(respuesta.context['ver_historial'])
                self.assertContains(respuesta, 'Historial de la incidencia')

    def test_vecino_del_edificio_ve_la_incidencia_pero_no_el_historial(self):
        self.client.force_login(self.beto)
        respuesta = self.client.get(self.url_detalle)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context['ver_historial'])
        self.assertNotContains(respuesta, 'Historial de la incidencia')

    def test_vecino_puede_comentar_pero_otro_edificio_no(self):
        url = reverse('incidencia_comentar', args=[self.i_ana.pk])
        self.client.force_login(self.beto)
        self.client.post(url, {'texto': 'A mí también me pasa'})
        self.assertEqual(self.i_ana.comentarios.count(), 1)
        self.client.force_login(self.carla)
        self.client.post(url, {'texto': 'Intruso'})
        self.assertEqual(self.i_ana.comentarios.count(), 1)

    def test_vecino_no_puede_editar_ni_eliminar_la_incidencia_ajena(self):
        self.client.force_login(self.beto)
        self.client.post(reverse('incidencia_eliminar', args=[self.i_ana.pk]))
        self.assertTrue(Incidencia.objects.filter(pk=self.i_ana.pk).exists())
        self.client.post(reverse('incidencia_editar', args=[self.i_ana.pk]), {
            'titulo': 'Título cambiado por vecino', 'descripcion': 'x',
            'categoria': 'agua', 'prioridad': 'baja',
        })
        self.i_ana.refresh_from_db()
        self.assertEqual(self.i_ana.titulo, 'Fuga de agua en el pasillo')

    def test_el_reparador_no_ve_el_historial(self):
        self.client.force_login(self.reparador_user)
        respuesta = self.client.get(self.url_detalle)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context['ver_historial'])
        self.assertNotContains(respuesta, 'Historial de la incidencia')

    def test_reparador_cambia_el_estado_de_su_incidencia(self):
        self.client.force_login(self.reparador_user)
        self.assertContains(self.client.get(self.url_detalle), 'Cambiar estado')
        self.client.post(self.url_estado, {'estado': dominio.EN_PROCESO})
        self.assertEqual(self._estado(), dominio.EN_PROCESO)
        self.client.post(self.url_estado, {'estado': dominio.RESUELTA})
        self.assertEqual(self._estado(), dominio.RESUELTA)
        ultimo = self.i_ana.eventos.last()
        self.assertEqual((ultimo.actor, ultimo.estado_nuevo), (self.reparador_user, 'resuelta'))

    def test_reparador_no_puede_saltarse_el_flujo_ni_cerrar(self):
        self.client.force_login(self.reparador_user)
        self.client.post(self.url_estado, {'estado': dominio.RESUELTA})  # pendiente -> resuelta
        self.assertEqual(self._estado(), dominio.PENDIENTE)
        self.client.post(self.url_estado, {'estado': dominio.CERRADA})
        self.assertEqual(self._estado(), dominio.PENDIENTE)
        self.client.post(self.url_estado, {'estado': dominio.EN_PROCESO})
        self.client.post(self.url_estado, {'estado': dominio.RESUELTA})
        self.client.post(self.url_estado, {'estado': dominio.CERRADA})
        self.assertEqual(self._estado(), dominio.RESUELTA)

    def test_reparador_no_cambia_el_estado_de_una_incidencia_no_asignada(self):
        url = reverse('incidencia_estado', args=[self.i_beto.pk])
        self.client.force_login(self.reparador_user)
        self.client.post(url, {'estado': dominio.EN_PROCESO})
        self.i_beto.refresh_from_db()
        self.assertEqual(self.i_beto.estado, dominio.PENDIENTE)

    def test_reparador_no_puede_gestionar_ni_reabrir(self):
        self.client.force_login(self.reparador_user)
        self.client.post(
            reverse('incidencia_gestionar', args=[self.i_ana.pk]),
            {'estado': dominio.EN_PROCESO, 'prioridad': 'alta', 'notas_internas': 'x'},
        )
        self.assertEqual(self._estado(), dominio.PENDIENTE)
        self.i_ana.refresh_from_db()
        self.assertEqual(self.i_ana.prioridad, 'media')

    def test_residente_y_otros_no_pueden_cambiar_el_estado(self):
        for usuario in (self.ana, self.beto, self.carla):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.client.post(self.url_estado, {'estado': dominio.EN_PROCESO})
                self.assertEqual(self._estado(), dominio.PENDIENTE)
