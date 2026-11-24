from datetime import timedelta

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from incidencias import dominio, services
from incidencias.models import Edificio, EventoIncidencia, Incidencia, Organizacion

from . import indicadores
from .routing import websocket_urlpatterns

User = get_user_model()
PAYLOAD = dict(
    titulo='Fuga de agua en el baño', descripcion='Gotea', categoria='agua', prioridad='media'
)


def montar(*, edificios=2):
    org = Organizacion.objects.create(nombre='Org')
    torres = [Edificio.objects.create(organizacion=org, nombre=f'Torre {i}') for i in range(edificios)]
    admin = User.objects.create_user('admin', password='x')
    admin.groups.add(Group.objects.get_or_create(name='Administrador')[0])
    usuarios = []
    for nombre, torre in zip(('ana', 'beto'), torres):
        u = User.objects.create_user(nombre, password='x')
        u.perfil.edificio = torre
        u.perfil.save()
        usuarios.append(u)
    return torres, admin, usuarios


def comunicador(ruta, usuario):
    c = WebsocketCommunicator(URLRouter(websocket_urlpatterns), ruta)
    c.scope['user'] = usuario
    return c


class WebSocketTest(TransactionTestCase):
    async def test_autorizacion_al_abrir_y_mensaje_en_vivo(self):
        torres, admin, (ana, beto) = await database_sync_to_async(montar)()
        inc = await database_sync_to_async(services.crear_incidencia)(
            residente=ana, edificio=torres[0], **PAYLOAD
        )

        # Un residente de otro edificio es rechazado al abrir la conexión
        ajeno = comunicador(f'/ws/incidencias/{inc.pk}/', beto)
        conectado, codigo = await ajeno.connect()
        self.assertFalse(conectado)

        # El dueño sí entra y recibe el cambio de estado
        dueno = comunicador(f'/ws/incidencias/{inc.pk}/', ana)
        conectado, _ = await dueno.connect()
        self.assertTrue(conectado)
        await database_sync_to_async(services.cambiar_estado)(inc, dominio.EN_PROCESO, actor=admin)
        mensaje = await dueno.receive_json_from(timeout=2)
        self.assertEqual(mensaje['estado'], 'en_proceso')
        self.assertEqual(mensaje['incidencia_id'], inc.pk)
        await dueno.disconnect()

    async def test_canal_de_edificio_solo_para_su_edificio_o_admin(self):
        torres, admin, (ana, beto) = await database_sync_to_async(montar)()
        c1 = comunicador(f'/ws/edificios/{torres[1].pk}/', ana)
        self.assertFalse((await c1.connect())[0])
        c2 = comunicador(f'/ws/edificios/{torres[0].pk}/', ana)
        self.assertTrue((await c2.connect())[0])
        c3 = comunicador(f'/ws/edificios/{torres[1].pk}/', admin)
        self.assertTrue((await c3.connect())[0])
        await c2.disconnect()
        await c3.disconnect()

    async def test_anonimo_rechazado(self):
        from django.contrib.auth.models import AnonymousUser

        c = comunicador('/ws/incidencias/1/', AnonymousUser())
        self.assertFalse((await c.connect())[0])


class IndicadoresTest(TestCase):
    def setUp(self):
        torres, self.admin, (self.ana, self.beto) = montar()
        self.torres = torres

    def resolver(self, residente, torre, horas, prioridad='media'):
        inc = services.crear_incidencia(
            residente=residente, edificio=torre, **{**PAYLOAD, 'prioridad': prioridad}
        )
        services.cambiar_estado(inc, dominio.EN_PROCESO, actor=self.admin)
        services.cambiar_estado(inc, dominio.RESUELTA, actor=self.admin)
        ahora = timezone.now()
        Incidencia.objects.filter(pk=inc.pk).update(creada=ahora - timedelta(hours=horas))
        return inc

    def test_indicadores_basicos(self):
        self.resolver(self.ana, self.torres[0], horas=10)                  # media: cumple (24 h)
        lenta = self.resolver(self.ana, self.torres[0], horas=30)          # media: incumple
        services.reabrir(lenta, actor=self.admin, motivo='Sigue mal')      # 1 reapertura
        d = indicadores.calcular(indicadores.filtros_desde({}))
        self.assertEqual(d['resueltas'], 2)
        self.assertEqual(d['cumplimiento_sla_pct'], 50.0)
        self.assertEqual(d['tasa_reapertura_pct'], 50.0)
        self.assertAlmostEqual(d['tiempo_medio_resolucion_horas'], 20.0, delta=0.1)
        self.assertEqual(d['abiertos_acumulados'], 1)   # la reabierta

    def test_filtro_por_edificio(self):
        self.resolver(self.ana, self.torres[0], horas=1)
        self.resolver(self.beto, self.torres[1], horas=1)
        d = indicadores.calcular(indicadores.filtros_desde({'edificio': str(self.torres[1].pk)}))
        self.assertEqual(d['resueltas'], 1)

    def test_sin_datos_no_divide_por_cero(self):
        d = indicadores.calcular(indicadores.filtros_desde({}))
        self.assertIsNone(d['cumplimiento_sla_pct'])
        self.assertIsNone(d['tiempo_medio_resolucion_horas'])
        self.assertEqual(d['serie_abiertos'], [])


class VistasTest(TestCase):
    def setUp(self):
        self.torres, self.admin, (self.ana, self.beto) = montar()

    def test_panel_solo_admin(self):
        self.client.force_login(self.ana)
        self.assertNotEqual(self.client.get('/panel/').status_code, 200)
        self.assertNotEqual(self.client.get('/panel/datos/').status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/panel/').status_code, 200)
        r = self.client.get('/panel/datos/', {'edificio': self.torres[0].pk})
        self.assertEqual(r.status_code, 200)
        self.assertIn('tasa_reapertura_pct', r.json())

    def test_en_vivo_detalle_de_otro_edificio_404(self):
        inc = services.crear_incidencia(residente=self.ana, edificio=self.torres[0], **PAYLOAD)
        self.client.force_login(self.beto)
        self.assertEqual(self.client.get(f'/en-vivo/{inc.pk}/').status_code, 404)
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(f'/en-vivo/{inc.pk}/').status_code, 200)

    def test_pwa_manifest_y_service_worker(self):
        r = self.client.get('/manifest.webmanifest')
        self.assertEqual(r.json()['display'], 'standalone')
        sw = self.client.get('/sw.js')
        self.assertEqual(sw['Service-Worker-Allowed'], '/')
        self.assertIn('addEventListener', sw.content.decode())
