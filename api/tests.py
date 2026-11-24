import io
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from PIL import Image
from rest_framework.test import APIClient

from eventos.models import WebhookEndpoint
from incidencias import dominio, services
from incidencias.models import Edificio, Incidencia, Organizacion, Tecnico

from .models import Adjunto
from .throttles import ThrottleUsuario

User = get_user_model()
BASE = '/api/v1/incidencias/'
PAYLOAD = {
    'titulo': 'Fuga de agua en el baño', 'descripcion': 'Gotea el techo',
    'categoria': 'agua', 'prioridad': 'alta',
}


def imagen_png():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buffer, 'PNG')
    return buffer.getvalue()


class BaseApiTest(TestCase):
    def setUp(self):
        cache.clear()  # los contadores de throttling viven en caché
        org = Organizacion.objects.create(nombre='Org')
        self.torre_a = Edificio.objects.create(organizacion=org, nombre='Torre A')
        self.torre_b = Edificio.objects.create(organizacion=org, nombre='Torre B')

        self.admin = User.objects.create_user('admin', password='clave-segura-1')
        self.admin.groups.add(Group.objects.get_or_create(name='Administrador')[0])
        self.ana = self._residente('ana', self.torre_a)
        self.beto = self._residente('beto', self.torre_b)

        self.tecnico = Tecnico.objects.create(
            nombre='Tomás', usuario=User.objects.create_user('tomas', password='x')
        )
        self.tecnico.edificios.add(self.torre_a)
        self.otro_tecnico = Tecnico.objects.create(
            nombre='Otro', usuario=User.objects.create_user('otro', password='x')
        )
        self.otro_tecnico.edificios.add(self.torre_a)

        self.incidencia = services.crear_incidencia(
            residente=self.ana, edificio=self.torre_a, **PAYLOAD
        )
        self.client = APIClient()

    def _residente(self, nombre, edificio):
        usuario = User.objects.create_user(nombre, password='clave-segura-1', email=f'{nombre}@ej.com')
        usuario.perfil.edificio = edificio
        usuario.perfil.save()
        return usuario

    def como(self, usuario):
        self.client.force_authenticate(usuario)
        return self.client

    def url(self, sufijo=''):
        return f'{BASE}{self.incidencia.pk}/{sufijo}'


class AutenticacionTest(BaseApiTest):
    def test_sin_credenciales_401(self):
        self.assertEqual(self.client.get(BASE).status_code, 401)

    def test_jwt_con_rotacion_de_refresh(self):
        r = self.client.post('/api/v1/auth/token/', {'username': 'ana', 'password': 'clave-segura-1'})
        self.assertEqual(r.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + r.data['access'])
        self.assertEqual(self.client.get(BASE).status_code, 200)

        self.client.credentials()
        nuevo = self.client.post('/api/v1/auth/token/refresh/', {'refresh': r.data['refresh']})
        self.assertEqual(nuevo.status_code, 200)
        self.assertNotEqual(nuevo.data['refresh'], r.data['refresh'])
        # el refresh anterior quedó en la lista negra
        viejo = self.client.post('/api/v1/auth/token/refresh/', {'refresh': r.data['refresh']})
        self.assertEqual(viejo.status_code, 401)

    def test_limite_de_uso_por_usuario(self):
        with mock.patch.object(ThrottleUsuario, 'THROTTLE_RATES', {'usuario': '2/min'}):
            c = self.como(self.ana)
            codigos = [c.get(BASE).status_code for _ in range(3)]
        self.assertEqual(codigos, [200, 200, 429])


class AislamientoTest(BaseApiTest):
    def test_otro_edificio_recibe_404_y_no_la_ve_en_la_lista(self):
        c = self.como(self.beto)
        self.assertEqual(c.get(self.url()).status_code, 404)
        self.assertEqual(c.post(self.url('comentarios/'), {'texto': 'hola'}).status_code, 404)
        self.assertEqual(c.post(self.url('estado/'), {'estado': 'en_proceso'}).status_code, 404)
        self.assertEqual(c.get(BASE).data['results'], [])

    def test_mismo_edificio_la_ve(self):
        vecino = self._residente('carla', self.torre_a)
        self.assertEqual(self.como(vecino).get(self.url()).status_code, 200)


class CrearEIdempotenciaTest(BaseApiTest):
    def test_crear_201(self):
        r = self.como(self.ana).post(BASE, PAYLOAD, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['estado'], 'pendiente')
        self.assertEqual(r.data['edificio']['nombre'], 'Torre A')
        self.assertIn('/api/v1/incidencias/', r['Location'])
        evento = Incidencia.objects.get(pk=r.data['id']).eventos.get()
        self.assertEqual(evento.tipo, 'creada')

    def test_validacion_titulo_corto(self):
        r = self.como(self.ana).post(BASE, {**PAYLOAD, 'titulo': 'corto'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('titulo', r.data)

    def test_sin_edificio_403(self):
        sin = User.objects.create_user('sin', password='x')
        self.assertEqual(self.como(sin).post(BASE, PAYLOAD, format='json').status_code, 403)

    def test_reintento_con_la_misma_clave_no_duplica(self):
        c = self.como(self.ana)
        antes = Incidencia.objects.count()
        r1 = c.post(BASE, PAYLOAD, format='json', headers={'Idempotency-Key': 'abc-123'})
        r2 = c.post(BASE, PAYLOAD, format='json', headers={'Idempotency-Key': 'abc-123'})
        self.assertEqual((r1.status_code, r2.status_code), (201, 201))
        self.assertEqual(r1.data['id'], r2.data['id'])
        self.assertEqual(r2['Idempotent-Replayed'], 'true')
        self.assertEqual(Incidencia.objects.count(), antes + 1)

    def test_misma_clave_con_otro_cuerpo_422(self):
        c = self.como(self.ana)
        c.post(BASE, PAYLOAD, format='json', headers={'Idempotency-Key': 'k'})
        r = c.post(BASE, {**PAYLOAD, 'titulo': 'Otro problema distinto'}, format='json',
                   headers={'Idempotency-Key': 'k'})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data['codigo'], 'idempotency_key_reutilizada')

    def test_sin_clave_cada_post_crea_una(self):
        c = self.como(self.ana)
        antes = Incidencia.objects.count()
        c.post(BASE, PAYLOAD, format='json')
        c.post(BASE, PAYLOAD, format='json')
        self.assertEqual(Incidencia.objects.count(), antes + 2)

    def test_las_claves_son_por_usuario(self):
        vecina = self._residente('carla', self.torre_a)
        r1 = self.como(self.ana).post(BASE, PAYLOAD, format='json', headers={'Idempotency-Key': 'k'})
        r2 = self.como(vecina).post(BASE, PAYLOAD, format='json', headers={'Idempotency-Key': 'k'})
        self.assertNotEqual(r1.data['id'], r2.data['id'])

    def test_los_errores_no_se_guardan_y_se_puede_corregir(self):
        c = self.como(self.ana)
        mala = c.post(BASE, {**PAYLOAD, 'titulo': 'corto'}, format='json', headers={'Idempotency-Key': 'k2'})
        self.assertEqual(mala.status_code, 400)
        buena = c.post(BASE, PAYLOAD, format='json', headers={'Idempotency-Key': 'k2'})
        self.assertEqual(buena.status_code, 201)


class ListadoYCondicionalesTest(BaseApiTest):
    def test_paginacion_por_cursor_sin_repetidos(self):
        for i in range(24):
            services.crear_incidencia(
                residente=self.ana, edificio=self.torre_a, **{**PAYLOAD, 'titulo': f'Incidencia número {i:02d}'}
            )  # + la del setUp = 25
        c = self.como(self.ana)
        p1 = c.get(BASE).data
        self.assertEqual(len(p1['results']), 20)
        self.assertIsNotNone(p1['next'])
        p2 = c.get(p1['next']).data
        self.assertEqual(len(p2['results']), 5)
        self.assertIsNone(p2['next'])
        ids = [x['id'] for x in p1['results'] + p2['results']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_filtros(self):
        services.crear_incidencia(
            residente=self.ana, edificio=self.torre_a,
            **{**PAYLOAD, 'titulo': 'Luz del pasillo apagada', 'categoria': 'electricidad'},
        )
        r = self.como(self.ana).get(BASE, {'categoria': 'electricidad'})
        self.assertEqual([x['categoria'] for x in r.data['results']], ['electricidad'])

    def test_sin_n_mas_1_en_el_listado(self):
        c = self.como(self.ana)
        c.get(BASE)  # calienta (perfil del usuario, etc.)

        def consultas():
            with CaptureQueriesContext(connection) as ctx:
                c.get(BASE)
            return len(ctx)

        base = consultas()
        for i in range(10):
            inc = services.crear_incidencia(
                residente=self.ana, edificio=self.torre_a, **{**PAYLOAD, 'titulo': f'Incidencia número {i:02d}'}
            )
            Adjunto.objects.create(incidencia=inc, archivo='x.png', nombre_original='x', tipo_contenido='image/png', tamano=1)
        self.assertEqual(consultas(), base)

    def test_etag_y_304(self):
        c = self.como(self.ana)
        r = c.get(self.url())
        etag = r['ETag']
        self.assertTrue(etag)
        self.assertEqual(c.get(self.url(), headers={'If-None-Match': etag}).status_code, 304)
        services.cambiar_estado(self.incidencia, dominio.EN_PROCESO, actor=self.admin)
        r2 = c.get(self.url(), headers={'If-None-Match': etag})
        self.assertEqual(r2.status_code, 200)
        self.assertNotEqual(r2['ETag'], etag)


class CasosDeUsoTest(BaseApiTest):
    def test_admin_cambia_estado_y_queda_evento(self):
        r = self.como(self.admin).post(self.url('estado/'), {'estado': 'en_proceso'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['estado'], 'en_proceso')
        self.assertEqual(self.incidencia.eventos.last().tipo, 'estado_cambiado')

    def test_transicion_invalida_422_con_codigo(self):
        r = self.como(self.admin).post(self.url('estado/'), {'estado': 'resuelta'}, format='json')
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data['codigo'], 'transicion_invalida')

    def test_residente_no_cambia_estado(self):
        r = self.como(self.ana).post(self.url('estado/'), {'estado': 'en_proceso'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_tecnico_asignado_si_otro_tecnico_no_la_ve(self):
        services.asignar_tecnico(self.incidencia, self.tecnico, actor=self.admin)
        ok = self.como(self.tecnico.usuario).post(self.url('estado/'), {'estado': 'en_proceso'}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.como(self.otro_tecnico.usuario).get(self.url()).status_code, 404)

    def test_if_match_obsoleto_412(self):
        c = self.como(self.admin)
        etag = c.get(self.url())['ETag']
        services.cambiar_estado(self.incidencia, dominio.EN_PROCESO, actor=self.admin)  # alguien se adelantó
        r = c.post(self.url('estado/'), {'estado': 'pendiente'}, format='json', headers={'If-Match': etag})
        self.assertEqual(r.status_code, 412)
        vigente = c.get(self.url())['ETag']
        ok = c.post(self.url('estado/'), {'estado': 'pendiente'}, format='json', headers={'If-Match': vigente})
        self.assertEqual(ok.status_code, 200)

    def test_asignar_y_reabrir_solo_admin(self):
        self.assertEqual(
            self.como(self.ana).post(self.url('asignar/'), {'tecnico': self.tecnico.pk}, format='json').status_code, 403
        )
        r = self.como(self.admin).post(self.url('asignar/'), {'tecnico': self.tecnico.pk}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['tecnico']['nombre'], 'Tomás')
        malo = self.como(self.admin).post(self.url('asignar/'), {'tecnico': 99999}, format='json')
        self.assertEqual(malo.status_code, 400)

        Incidencia.objects.filter(pk=self.incidencia.pk).update(estado=dominio.RESUELTA)
        sin_motivo = self.como(self.admin).post(self.url('reabrir/'), {'motivo': ''}, format='json')
        self.assertEqual(sin_motivo.status_code, 400)
        ok = self.como(self.admin).post(self.url('reabrir/'), {'motivo': 'Sigue goteando'}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data['estado'], 'pendiente')

    def test_comentarios(self):
        c = self.como(self.ana)
        r = c.post(self.url('comentarios/'), {'texto': '  Hola  '}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['texto'], 'Hola')
        self.assertEqual(c.post(self.url('comentarios/'), {'texto': '   '}, format='json').status_code, 400)
        lista = c.get(self.url('comentarios/'))
        self.assertEqual([x['autor'] for x in lista.data], ['ana'])
        self.assertEqual(c.get(self.url()).data['total_comentarios'], 1)


class AdjuntosTest(BaseApiTest):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        sobreescribir = override_settings(MEDIA_ROOT=self.media)
        sobreescribir.enable()
        self.addCleanup(sobreescribir.disable)

    def test_imagen_real_se_acepta_y_el_tipo_sale_del_contenido(self):
        archivo = SimpleUploadedFile('foto.txt', imagen_png(), content_type='text/plain')  # miente
        r = self.como(self.ana).post(self.url('adjuntos/'), {'archivo': archivo}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['tipo_contenido'], 'image/png')
        self.assertTrue(Adjunto.objects.get().archivo.name.endswith('.png'))

    def test_archivo_falso_con_extension_png_se_rechaza(self):
        archivo = SimpleUploadedFile('virus.png', b'esto no es una imagen', content_type='image/png')
        r = self.como(self.ana).post(self.url('adjuntos/'), {'archivo': archivo}, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Adjunto.objects.count(), 0)

    def test_pdf_por_firma(self):
        archivo = SimpleUploadedFile('doc.pdf', b'%PDF-1.4 contenido', content_type='application/pdf')
        r = self.como(self.ana).post(self.url('adjuntos/'), {'archivo': archivo}, format='multipart')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['tipo_contenido'], 'application/pdf')

    def test_vecino_del_mismo_edificio_no_puede_adjuntar(self):
        vecina = self._residente('carla', self.torre_a)
        archivo = SimpleUploadedFile('a.png', imagen_png())
        r = self.como(vecina).post(self.url('adjuntos/'), {'archivo': archivo}, format='multipart')
        self.assertEqual(r.status_code, 403)


class WebhooksTest(BaseApiTest):
    DATOS = {'edificio': None, 'url': 'https://cliente.test/hook', 'eventos': ['incidencia.resuelta']}

    def test_solo_admin(self):
        r = self.como(self.ana).get('/api/v1/webhooks/')
        self.assertEqual(r.status_code, 403)

    def test_el_secreto_solo_se_muestra_al_crear(self):
        c = self.como(self.admin)
        r = c.post('/api/v1/webhooks/', {**self.DATOS, 'edificio': self.torre_a.pk}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertGreaterEqual(len(r.data['secreto']), 32)
        self.assertEqual(WebhookEndpoint.objects.get().secreto, r.data['secreto'])
        self.assertNotIn('secreto', c.get('/api/v1/webhooks/').data[0])
        self.assertNotIn('secreto', c.get(f"/api/v1/webhooks/{r.data['id']}/").data)

    def test_validaciones(self):
        c = self.como(self.admin)
        malo = c.post('/api/v1/webhooks/', {**self.DATOS, 'edificio': self.torre_a.pk, 'eventos': ['inventado']}, format='json')
        self.assertEqual(malo.status_code, 400)
        ftp = c.post('/api/v1/webhooks/', {**self.DATOS, 'edificio': self.torre_a.pk, 'url': 'ftp://x.test/a'}, format='json')
        self.assertEqual(ftp.status_code, 400)


class ContratoOpenApiTest(BaseApiTest):
    def test_el_esquema_se_genera_y_es_valido(self):
        salida = io.StringIO()
        call_command('spectacular', '--validate', stdout=salida, stderr=io.StringIO())
        self.assertIn('openapi', salida.getvalue())

    def test_el_esquema_se_sirve_y_documenta_las_operaciones_clave(self):
        r = self.client.get('/api/v1/schema/', {'format': 'json'}, headers={'Accept': 'application/vnd.oai.openapi+json'})
        self.assertEqual(r.status_code, 200)
        rutas = r.json()['paths']
        for ruta in ('/api/v1/incidencias/', '/api/v1/incidencias/{id}/estado/', '/api/v1/webhooks/',
                     '/api/v1/auth/token/refresh/'):
            self.assertIn(ruta, rutas)
        parametros = [p['name'] for p in rutas['/api/v1/incidencias/']['post']['parameters']]
        self.assertIn('Idempotency-Key', parametros)

    def test_las_migraciones_de_api_y_eventos_estan_al_dia(self):
        call_command('makemigrations', 'api', 'eventos', '--check', '--dry-run',
                     stdout=io.StringIO(), stderr=io.StringIO())
