from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/incidencias/<int:pk>/', consumers.IncidenciaConsumer.as_asgi()),
    path('ws/edificios/<int:pk>/', consumers.EdificioConsumer.as_asgi()),
]
