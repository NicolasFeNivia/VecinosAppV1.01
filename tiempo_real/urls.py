from django.urls import path

from . import views

urlpatterns = [
    path('en-vivo/', views.EnVivoListaView.as_view(), name='en_vivo_lista'),
    path('en-vivo/<int:pk>/', views.EnVivoDetalleView.as_view(), name='en_vivo_detalle'),
    path('panel/', views.PanelView.as_view(), name='panel'),
    path('panel/datos/', views.PanelDatosView.as_view(), name='panel_datos'),
    path('tecnico/', views.TecnicoAppView.as_view(), name='tecnico_app'),
    path('manifest.webmanifest', views.ManifestView.as_view(), name='manifest'),
    path('sw.js', views.ServiceWorkerView.as_view(), name='service_worker'),
]
