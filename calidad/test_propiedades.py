"""M7: pruebas de propiedades con Hypothesis sobre los casos de uso (secuencias aleatorias)."""
import unittest

try:
    from hypothesis import HealthCheck, given, settings, strategies as st
    from hypothesis.extra.django import TestCase as HypothesisTestCase
except ImportError:  # pip install hypothesis
    raise unittest.SkipTest('hypothesis no está instalado')

from django.contrib.auth import get_user_model

from incidencias import dominio, services
from incidencias.models import Edificio, Organizacion

User = get_user_model()
ESTADOS = [dominio.PENDIENTE, dominio.EN_PROCESO, dominio.RESUELTA, dominio.CERRADA]
OPERACION = st.one_of(
    st.tuples(st.just('estado'), st.sampled_from(ESTADOS)),
    st.tuples(st.just('reabrir'), st.sampled_from(['', 'Sigue goteando'])),
)


class SecuenciasAleatoriasTest(HypothesisTestCase):
    @settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(operaciones=st.lists(OPERACION, max_size=15))
    def test_invariantes_tras_cualquier_secuencia(self, operaciones):
        org, _ = Organizacion.objects.get_or_create(nombre='Org')
        edificio, _ = Edificio.objects.get_or_create(organizacion=org, nombre='Torre A')
        user, _ = User.objects.get_or_create(username='ana')
        inc = services.crear_incidencia(
            residente=user, edificio=edificio, titulo='Fuga de agua en el baño',
            descripcion='x', categoria='agua', prioridad='alta',
        )
        exitosas = 0
        for tipo, valor in operaciones:
            try:
                if tipo == 'estado':
                    services.cambiar_estado(inc, valor, actor=user)
                else:
                    services.reabrir(inc, actor=user, motivo=valor)
                exitosas += 1
            except dominio.DominioError:
                pass
            inc.refresh_from_db()
            self.assertIn(inc.estado, ESTADOS)

        eventos = list(inc.eventos.all())
        # 1 evento de creación + uno por operación exitosa; las rechazadas no dejan rastro
        self.assertEqual(len(eventos), 1 + exitosas)
        # La cadena de estados es continua: cada cambio parte de donde terminó el anterior
        actual = dominio.PENDIENTE
        for evento in eventos[1:]:
            self.assertEqual(evento.estado_anterior, actual)
            actual = evento.estado_nuevo
        self.assertEqual(actual, inc.estado)
        # Y cada paso fue legal según el dominio
        for evento in eventos[1:]:
            if evento.tipo == 'reabierta':
                self.assertTrue(dominio.puede_reabrir(evento.estado_anterior))
            else:
                self.assertTrue(dominio.puede_pasar(evento.estado_anterior, evento.estado_nuevo))
