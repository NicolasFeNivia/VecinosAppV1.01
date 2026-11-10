from .mixins import es_admin


def rol(request):
    """Deja disponible la variable `es_admin` en todas las plantillas."""
    usuario = getattr(request, 'user', None)
    return {'es_admin': es_admin(usuario) if usuario is not None else False}
