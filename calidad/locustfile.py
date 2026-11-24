"""M7: prueba de carga con Locust contra la API (M4).

    locust -f calidad/locustfile.py --host http://localhost:8000 --users 50 --spawn-rate 5 \
           --run-time 1m --headless
    Variables: VECINOS_USER, VECINOS_PASS
"""
import os
import uuid

from locust import HttpUser, between, task


class Residente(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        r = self.client.post('/api/v1/auth/token/', json={
            'username': os.environ.get('VECINOS_USER', 'ana'),
            'password': os.environ.get('VECINOS_PASS', 'cambiame'),
        })
        self.client.headers['Authorization'] = 'Bearer ' + r.json()['access']

    @task(6)
    def listar(self):
        self.client.get('/api/v1/incidencias/', name='/incidencias/')

    @task(2)
    def filtrar(self):
        self.client.get('/api/v1/incidencias/?estado=pendiente&q=agua', name='/incidencias/?filtros')

    @task(1)
    def crear(self):
        self.client.post(
            '/api/v1/incidencias/',
            json={'titulo': 'Prueba de carga de la API', 'descripcion': 'x', 'categoria': 'otros'},
            headers={'Idempotency-Key': uuid.uuid4().hex},
            name='POST /incidencias/',
        )
