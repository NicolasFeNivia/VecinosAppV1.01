"""Reglas puras del dominio: sin Django, sin base de datos."""

PENDIENTE = 'pendiente'
EN_PROCESO = 'en_proceso'
RESUELTA = 'resuelta'
CERRADA = 'cerrada'

# Tabla de transiciones explícita (cambios normales de estado)
TRANSICIONES = {
    PENDIENTE: {EN_PROCESO, CERRADA},
    EN_PROCESO: {PENDIENTE, RESUELTA},
    RESUELTA: {CERRADA},
    CERRADA: set(),
}

# Estados desde los que se puede reabrir (siempre vuelve a PENDIENTE)
REABRIBLES = {RESUELTA, CERRADA}
DESTINO_REAPERTURA = PENDIENTE


class DominioError(Exception):
    """Error base de las reglas de negocio."""


class TransicionInvalida(DominioError):
    pass


class AsignacionInvalida(DominioError):
    pass


def puede_pasar(origen, destino):
    return destino in TRANSICIONES.get(origen, set())


def puede_reabrir(estado):
    return estado in REABRIBLES
