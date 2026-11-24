from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import IncidenciaViewSet, WebhookViewSet

app_name = 'api'

router = SimpleRouter()
router.register('incidencias', IncidenciaViewSet, basename='incidencia')
router.register('webhooks', WebhookViewSet, basename='webhook')

urlpatterns = [
    path('v1/auth/token/', TokenObtainPairView.as_view(), name='token'),
    path('v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('v1/auth/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),
    path('v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('v1/docs/', SpectacularSwaggerView.as_view(url_name='api:schema'), name='docs'),
    path('v1/', include(router.urls)),
]
