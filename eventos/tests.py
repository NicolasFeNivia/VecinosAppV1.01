import json
from datetime import timedelta
from unittest import mock
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from incidencias import dominio, services
from incidencias.models import Edificio, Incidencia, Organizacion

from . import firma, servicios, sla
from .canales import CANALES
from .models import Outbox, PreferenciaNotificacion, WebhookEndpoint

User = get_user_model()


class WorkerCaido(BaseException):
    """Simula que el proceso del worker muere a mitad del envío (no es una Exception)."""


class FirmaTest(SimpleTestCase):
    def test_firma_valida(self):
        cabecera = firma.firmar('secreto', b'{"a":1}', timestamp=1000)
        self.assertTrue(firma.verificar('secreto', cabecera, b'{"a":1}', ahora=1010))

    def test_cuerpo_alterado_o_secreto_distinto(self):
        cabecera = firma.firmar('secreto', b'{"a":1}', timestamp=1000)
        self.assertFalse(firma.verificar('secreto', cabecera, b'{"a":2}', ahora=1010))
        self.assertFalse(firma.verificar('otro', cabecera, b'{"a":1}', ahora=1010))

    def test_marca_de_tiempo_vieja_se_rechaza(self):
        cabecera = firma.firmar('secreto', b'x', timestamp=1000)
        self.assertFalse(firma.verificar('secreto', cabecera, b'x', ahora=1000 + 301))

    def test_cabecera_malformada(self):
        self.assertFalse(firma.verificar('s', 'basura', b'x'))

    def test_backoff_exponencial_con_tope(self):
        self.assertEqual([servicios.espera_backoff(i) for i in (1, 2, 3)], [30, 60, 120])
        self.assertEqual(servicios.espera_backoff(50), servicios.BACKOFF_MAX_SEGUNDOS)


class BaseOutboxTest(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre='Org')
        self.edificio = Edificio.objects.create(organizacion=org, nombre='Torre A')
        self.admin_edificio = User.objects.create_user('jefe', password='x', email='jefe@ej.com')
        self.edificio.administradores.add(self.admin_edificio)
        self.actor = User.objects.create_user('admin', password='x')
        self.residente = User.objects.create_user('ana', password='x', email='ana@ej.com')
        self.incidencia = services.crear_incidencia(
            residente=self.residente, edificio=self.edificio, titulo='Fuga de agua en el baño',
            descripcion='Gotea', categoria='agua', prioridad='media',
        )
        self.endpoint = WebhookEndpoint.objects.create(
            edificio=self.edificio, url='https://cliente.test/hook', secreto='s3cr3to',
            eventos=['incidencia.resuelta'],
        )

    def resolver(self):
        services.cambiar_estado(self.incidencia, dominio.EN_PROCESO, actor=self.actor)
        services.cambiar_estado(self.incidencia, dominio.RESUELTA, actor=self.actor)


class EscrituraOutboxTest(BaseOutboxTest):
    def test_resolver_encola_correo_y_webhook_sin_enviar_nada_todavia(self):
        self.resolver()
        mensajes = Outbox.objects.filter(tipo='incidencia.resuelta')
        self.assertEqual(sorted(m.canal for m in mensajes), ['correo', 'webhook'])
        self.assertEqual(len(mail.outbox), 0)  # el post_save del MVP ya no envía

    def test_webhook_solo_si_el_endpoint_esta_suscrito(self):
        self.endpoint.eventos = ['incidencia.reabierta']
        self.endpoint.save()
        self.resolver()
        self.assertFalse(Outbox.objects.filter(canal='webhook').exists())

    def test_preferencia_desactivada_no_encola_correo(self):
        PreferenciaNotificacion.objects.create(
            usuario=self.residente, canal='correo', evento='incidencia.resuelta', activo=False
        )
        self.resolver()
        self.assertFalse(Outbox.objects.filter(canal='correo').exists())

    def test_si_la_transaccion_se_revierte_no_queda_mensaje(self):
        antes = Outbox.objects.count()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                services.cambiar_estado(self.incidencia, dominio.EN_PROCESO, actor=self.actor)
                services.cambiar_estado(self.incidencia, dominio.RESUELTA, actor=self.actor)
                raise RuntimeError('falla a mitad del cambio')
        self.assertEqual(Outbox.objects.count(), antes)
        self.incidencia.refresh_from_db()
        self.assertEqual(self.incidencia.estado, dominio.PENDIENTE)

    def test_encolar_es_idempotente(self):
        a = servicios.encolar(tipo='t', canal='correo', destino='x@y.com', payload={}, clave='k1')
        b = servicios.encolar(tipo='t', canal='correo', destino='x@y.com', payload={}, clave='k1')
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Outbox.objects.filter(clave_dedupe='k1').count(), 1)

    def test_al_confirmar_se_publica_en_celery(self):
        with mock.patch('eventos.tasks.entregar_mensaje.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                self.resolver()
        publicados = {c.args[0] for c in delay.call_args_list}
        self.assertTrue(set(Outbox.objects.values_list('pk', flat=True)) >= publicados)
        self.assertEqual(len(publicados), 2)


class EntregaTest(BaseOutboxTest):
    def setUp(self):
        super().setUp()
        self.resolver()
        self.correo = Outbox.objects.get(canal='correo')
        self.webhook = Outbox.objects.get(canal='webhook')

    def test_correo_se_entrega_una_sola_vez(self):
        self.assertEqual(servicios.entregar(self.correo.pk), 'entregado')
        self.assertEqual(servicios.entregar(self.correo.pk), 'omitido')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['ana@ej.com'])
        self.correo.refresh_from_db()
        self.assertEqual(self.correo.estado, Outbox.ENTREGADO)

    def test_webhook_firmado_y_con_id_de_entrega(self):
        with mock.patch('eventos.canales.urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            self.assertEqual(servicios.entregar(self.webhook.pk), 'entregado')
        peticion = urlopen.call_args.args[0]
        cuerpo = peticion.data
        self.assertTrue(
            firma.verificar('s3cr3to', peticion.get_header('X-vecinos-signature'), cuerpo)
        )
        self.assertEqual(peticion.get_header('X-vecinos-delivery'), str(self.webhook.pk))
        self.assertEqual(json.loads(cuerpo)['tipo'], 'incidencia.resuelta')

    def test_fallo_programa_reintento_con_backoff_y_luego_entrega(self):
        ahora = timezone.now()
        with mock.patch.object(CANALES['correo'], 'enviar', side_effect=OSError('smtp caído')):
            self.assertEqual(servicios.entregar(self.correo.pk, ahora=ahora), 'reintento')
        self.correo.refresh_from_db()
        self.assertEqual((self.correo.estado, self.correo.intentos), (Outbox.PENDIENTE, 1))
        self.assertEqual(self.correo.proximo_intento, ahora + timedelta(seconds=30))
        # Antes de su turno no se toca
        self.assertEqual(servicios.entregar(self.correo.pk, ahora=ahora + timedelta(seconds=5)), 'omitido')
        # Llegado el turno se entrega
        self.assertEqual(servicios.entregar(self.correo.pk, ahora=ahora + timedelta(seconds=31)), 'entregado')
        self.assertEqual(len(mail.outbox), 1)

    def test_webhook_con_error_http_se_reintenta_y_agotados_los_intentos_va_a_fallidos(self):
        ahora = timezone.now()
        error = HTTPError('https://cliente.test/hook', 500, 'boom', {}, None)
        with mock.patch('eventos.canales.urlopen', side_effect=error):
            resultado = None
            for i in range(servicios.MAX_INTENTOS):
                resultado = servicios.entregar(self.webhook.pk, ahora=ahora + timedelta(days=i + 1))
        self.assertEqual(resultado, 'fallido')
        self.webhook.refresh_from_db()
        self.assertEqual(self.webhook.estado, Outbox.FALLIDO)
        self.assertEqual(servicios.entregar(self.webhook.pk, ahora=ahora + timedelta(days=99)), 'omitido')

    def test_endpoint_inexistente_va_directo_a_fallidos(self):
        self.endpoint.delete()
        self.assertEqual(servicios.entregar(self.webhook.pk), 'fallido')


class PruebaDeCaosTest(BaseOutboxTest):
    """El worker muere durante el envío: el mensaje llega una sola vez al recuperarse."""

    def setUp(self):
        super().setUp()
        self.resolver()
        self.correo = Outbox.objects.get(canal='correo')

    def test_worker_muere_a_mitad_del_envio(self):
        ahora = timezone.now()
        with mock.patch.object(CANALES['correo'], 'enviar', side_effect=WorkerCaido()):
            with self.assertRaises(WorkerCaido):
                servicios.entregar(self.correo.pk, ahora=ahora)
        self.correo.refresh_from_db()
        self.assertEqual(self.correo.estado, Outbox.ENVIANDO)  # quedó reclamado, sin entregar
        self.assertEqual(len(mail.outbox), 0)

        # Mientras el lease sigue vigente nadie más lo toca (no hay doble envío concurrente)
        self.assertEqual(servicios.entregar(self.correo.pk, ahora=ahora + timedelta(seconds=10)), 'omitido')
        self.assertEqual(servicios.pendientes_vencidos(ahora + timedelta(seconds=10)), [])

        # Vencido el lease, beat lo detecta y otro worker lo entrega
        despues = ahora + timedelta(seconds=servicios.LEASE_SEGUNDOS + 1)
        self.assertEqual(servicios.pendientes_vencidos(despues), [self.correo.pk])
        self.assertEqual(servicios.entregar(self.correo.pk, ahora=despues), 'entregado')
        self.assertEqual(servicios.entregar(self.correo.pk, ahora=despues), 'omitido')
        self.assertEqual(len(mail.outbox), 1)  # exactamente uno

    def test_si_redis_cae_el_mensaje_sigue_en_la_tabla_y_beat_lo_recoge(self):
        with mock.patch('eventos.tasks.entregar_mensaje.delay', side_effect=ConnectionError):
            servicios.despachar_mensajes([self.correo.pk])  # no debe lanzar
        self.assertIn(self.correo.pk, servicios.pendientes_vencidos())


class SlaTest(BaseOutboxTest):
    def envejecer(self, horas):
        Incidencia.objects.filter(pk=self.incidencia.pk).update(
            creada=timezone.now() - timedelta(hours=horas)
        )

    def test_dentro_del_plazo_no_escala(self):
        self.envejecer(1)
        self.assertEqual(sla.escalar_fuera_de_sla(), [])

    def test_fuera_de_sla_avisa_al_admin_del_edificio_y_sube_prioridad_una_sola_vez(self):
        self.envejecer(25)  # prioridad media: 24 h
        self.assertEqual(sla.escalar_fuera_de_sla(), [self.incidencia.pk])
        self.incidencia.refresh_from_db()
        self.assertEqual(self.incidencia.prioridad, 'alta')
        aviso = Outbox.objects.get(tipo='incidencia.sla_vencida', canal='correo')
        self.assertEqual(aviso.destino, 'jefe@ej.com')
        self.assertEqual(sla.escalar_fuera_de_sla(), [])  # segunda corrida: nada nuevo
        self.assertEqual(Outbox.objects.filter(tipo='incidencia.sla_vencida', canal='correo').count(), 1)

    def test_las_resueltas_no_escalan(self):
        self.envejecer(100)
        Incidencia.objects.filter(pk=self.incidencia.pk).update(estado=dominio.RESUELTA)
        self.assertEqual(sla.escalar_fuera_de_sla(), [])
