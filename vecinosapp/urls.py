from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('incidencias.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# M4: API versionada en /api/v1/
urlpatterns += [path('api/', include('api.urls'))]

# M6: páginas en vivo, panel de indicadores y app del técnico (PWA)
urlpatterns += [path('', include('tiempo_real.urls'))]
