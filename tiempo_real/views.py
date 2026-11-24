import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.templatetags.static import static
from django.views import View
from django.views.generic import TemplateView

from incidencias.mixins import AdminRequiredMixin, es_admin, tecnico_de
from incidencias.models import Edificio, Tecnico
from incidencias.views import incidencias_visibles

from . import indicadores


class EnVivoListaView(LoginRequiredMixin, TemplateView):
    """Lista de incidencias que se actualiza sola por WebSocket (canal del edificio)."""

    template_name = 'tiempo_real/en_vivo_lista.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['incidencias'] = list(incidencias_visibles(user)[:50])
        perfil = getattr(user, 'perfil', None)
        # El canal de edificio es para residentes del edificio; el admin ve todos.
        ctx['edificios_ws'] = (
            list(Edificio.objects.values_list('pk', flat=True)) if es_admin(user)
            else ([perfil.edificio_id] if perfil and perfil.edificio_id else [])
        )
        return ctx


class EnVivoDetalleView(LoginRequiredMixin, TemplateView):
    template_name = 'tiempo_real/en_vivo_detalle.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['incidencia'] = get_object_or_404(incidencias_visibles(self.request.user), pk=self.kwargs['pk'])
        return ctx


class PanelView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = 'tiempo_real/panel.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['edificios'] = Edificio.objects.order_by('nombre')
        ctx['tecnicos'] = Tecnico.objects.order_by('nombre')
        return ctx


class PanelDatosView(LoginRequiredMixin, AdminRequiredMixin, View):
    def get(self, request):
        return JsonResponse(indicadores.calcular(indicadores.filtros_desde(request.GET)))


class TecnicoAppView(LoginRequiredMixin, TemplateView):
    """Aplicación web mínima e instalable (PWA) para el técnico."""

    template_name = 'tiempo_real/tecnico.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tecnico = tecnico_de(self.request.user)
        ctx['incidencias'] = list(incidencias_visibles(self.request.user)[:50]) if tecnico else []
        return ctx


class ManifestView(View):
    def get(self, request):
        datos = {
            'name': 'VecinosApp Técnico',
            'short_name': 'Vecinos',
            'start_url': '/tecnico/',
            'scope': '/',
            'display': 'standalone',
            'background_color': '#212529',
            'theme_color': '#212529',
            'icons': [
                {'src': static('tiempo_real/icono.svg'), 'sizes': 'any', 'type': 'image/svg+xml'}
            ],
        }
        return JsonResponse(datos, content_type='application/manifest+json')


class ServiceWorkerView(View):
    """Debe servirse desde la raíz para controlar todo el sitio."""

    def get(self, request):
        from django.http import HttpResponse

        js = (
            "const CACHE='vecinos-v1';\n"
            "self.addEventListener('install',e=>{self.skipWaiting();});\n"
            "self.addEventListener('activate',e=>{e.waitUntil(clients.claim());});\n"
            "self.addEventListener('fetch',e=>{\n"
            "  if(e.request.method!=='GET'||e.request.url.includes('/ws/'))return;\n"
            "  e.respondWith(fetch(e.request).then(r=>{\n"
            "    const copia=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copia));return r;\n"
            "  }).catch(()=>caches.match(e.request)));\n"
            "});\n"
        )
        respuesta = HttpResponse(js, content_type='application/javascript')
        respuesta['Service-Worker-Allowed'] = '/'
        return respuesta
