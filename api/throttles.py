from rest_framework.throttling import SimpleRateThrottle


class ThrottleUsuario(SimpleRateThrottle):
    """Límite por usuario (o por IP si es anónimo, p. ej. en el login)."""

    scope = 'usuario'

    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user and request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class ThrottleEdificio(SimpleRateThrottle):
    """Límite compartido por todos los usuarios de un mismo edificio."""

    scope = 'edificio'

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        perfil = getattr(request.user, 'perfil', None)
        if perfil is None or not perfil.edificio_id:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': perfil.edificio_id}
