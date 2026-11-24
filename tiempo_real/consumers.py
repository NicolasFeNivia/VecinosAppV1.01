from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from incidencias.mixins import es_admin
from incidencias.views import incidencias_visibles


def grupo_incidencia(pk):
    return f'incidencia_{pk}'


def grupo_edificio(pk):
    return f'edificio_{pk}'


@database_sync_to_async
def _puede_ver_incidencia(user, pk):
    return incidencias_visibles(user).filter(pk=pk).exists()


@database_sync_to_async
def _puede_ver_edificio(user, pk):
    if es_admin(user):
        return True
    perfil = getattr(user, 'perfil', None)
    return perfil is not None and perfil.edificio_id == pk


class _Base(AsyncJsonWebsocketConsumer):
    """La autorización se decide AL ABRIR la conexión; si falla, se cierra con 4403."""

    async def puede(self, user, pk):
        raise NotImplementedError

    def grupo(self, pk):
        raise NotImplementedError

    async def connect(self):
        user = self.scope.get('user')
        pk = self.scope['url_route']['kwargs']['pk']
        if user is None or not user.is_authenticated or not await self.puede(user, pk):
            await self.close(code=4403)
            return
        self.nombre_grupo = self.grupo(pk)
        await self.channel_layer.group_add(self.nombre_grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, 'nombre_grupo'):
            await self.channel_layer.group_discard(self.nombre_grupo, self.channel_name)

    async def incidencia_evento(self, evento):
        await self.send_json(evento['datos'])


class IncidenciaConsumer(_Base):
    async def puede(self, user, pk):
        return await _puede_ver_incidencia(user, pk)

    def grupo(self, pk):
        return grupo_incidencia(pk)


class EdificioConsumer(_Base):
    async def puede(self, user, pk):
        return await _puede_ver_edificio(user, pk)

    def grupo(self, pk):
        return grupo_edificio(pk)
