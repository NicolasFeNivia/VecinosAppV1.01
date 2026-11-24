from .mixins import es_admin, es_reparador


def rol(request):
    """Deja disponibles `es_admin` y `es_reparador` en todas las plantillas."""
    usuario = getattr(request, 'user', None)
    if usuario is None:
        return {'es_admin': False, 'es_reparador': False}
    return {'es_admin': es_admin(usuario), 'es_reparador': es_reparador(usuario)}
