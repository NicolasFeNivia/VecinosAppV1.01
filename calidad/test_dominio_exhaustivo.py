"""M7: el dominio es puro, así que se prueba COMPLETO (todas las combinaciones) sin base de datos."""
import itertools
import unittest

from incidencias import dominio

ESTADOS = [dominio.PENDIENTE, dominio.EN_PROCESO, dominio.RESUELTA, dominio.CERRADA]


class TablaDeTransicionesTest(unittest.TestCase):
    def test_todas_las_parejas_coinciden_con_la_tabla(self):
        for origen, destino in itertools.product(ESTADOS, repeat=2):
            with self.subTest(origen=origen, destino=destino):
                self.assertEqual(
                    dominio.puede_pasar(origen, destino), destino in dominio.TRANSICIONES[origen]
                )

    def test_la_tabla_es_cerrada(self):
        self.assertEqual(set(dominio.TRANSICIONES), set(ESTADOS))
        for destinos in dominio.TRANSICIONES.values():
            self.assertTrue(destinos <= set(ESTADOS))

    def test_ningun_estado_pasa_a_si_mismo(self):
        for estado in ESTADOS:
            self.assertFalse(dominio.puede_pasar(estado, estado))

    def test_cerrada_es_terminal(self):
        self.assertEqual(dominio.TRANSICIONES[dominio.CERRADA], set())

    def test_estado_desconocido_nunca_pasa(self):
        self.assertFalse(dominio.puede_pasar('inventado', dominio.PENDIENTE))
        self.assertFalse(dominio.puede_pasar(dominio.PENDIENTE, 'inventado'))

    def test_reapertura(self):
        for estado in ESTADOS:
            self.assertEqual(dominio.puede_reabrir(estado), estado in (dominio.RESUELTA, dominio.CERRADA))
        self.assertIn(dominio.DESTINO_REAPERTURA, ESTADOS)

    def test_toda_incidencia_puede_llegar_a_cerrada(self):
        """Desde cualquier estado hay un camino hasta CERRADA (nadie queda atrapado)."""
        for inicio in ESTADOS:
            visto, pendientes = {inicio}, [inicio]
            while pendientes:
                for sig in dominio.TRANSICIONES[pendientes.pop()]:
                    if sig not in visto:
                        visto.add(sig)
                        pendientes.append(sig)
            self.assertIn(dominio.CERRADA, visto, inicio)

    def test_jerarquia_de_errores(self):
        self.assertTrue(issubclass(dominio.TransicionInvalida, dominio.DominioError))
        self.assertTrue(issubclass(dominio.AsignacionInvalida, dominio.DominioError))
