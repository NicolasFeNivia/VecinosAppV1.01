"""M7: concurrencia real. Solo en PostgreSQL (SQLite no soporta bien escrituras desde hilos).

    DB_ENGINE=postgres python manage.py test calidad.test_concurrencia
"""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from eventos import servicios
from eventos.models import Outbox
from incidencias import dominio, services
from incidencias.models import Edificio, Organizacion

User = get_user_model()


@unittest.skipUnless(connection.vendor == 'postgresql', 'requiere PostgreSQL')
class EntregaConcurrenteTest(TransactionTestCase):
    def test_20_workers_sobre_el_mismo_mensaje_envian_una_sola_vez(self):
        org = Organizacion.objects.create(nombre='Org')
        edificio = Edificio.objects.create(organizacion=org, nombre='Torre A')
        actor = User.objects.create_user('admin', password='x')
        ana = User.objects.create_user('ana', password='x', email='ana@ej.com')
        inc = services.crear_incidencia(
            residente=ana, edificio=edificio, titulo='Fuga de agua en el baño',
            descripcion='x', categoria='agua', prioridad='alta',
        )
        services.cambiar_estado(inc, dominio.EN_PROCESO, actor=actor)
        services.cambiar_estado(inc, dominio.RESUELTA, actor=actor)
        mensaje = Outbox.objects.get(canal='correo')
        ahora = timezone.now() + timedelta(seconds=1)

        def worker(_):
            try:
                return servicios.entregar(mensaje.pk, ahora=ahora)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=20) as pool:
            resultados = list(pool.map(worker, range(20)))

        self.assertEqual(resultados.count('entregado'), 1)
        self.assertEqual(len(mail.outbox), 1)
