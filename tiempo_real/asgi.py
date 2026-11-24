"""ASGI: HTTP normal de Django + WebSockets. Se activa con ASGI_APPLICATION en settings."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vecinosapp.settings')
django_asgi = get_asgi_application()  # debe ir antes de importar los consumidores

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from .routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        'http': django_asgi,
        'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
