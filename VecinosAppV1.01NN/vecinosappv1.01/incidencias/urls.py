from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    path('', views.InicioView.as_view(), name='inicio'),

    path('registro/', views.RegistroView.as_view(), name='registro'),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='incidencias/login.html',
            authentication_form=LoginForm,
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('perfil/', views.PerfilUpdateView.as_view(), name='perfil'),

    path('incidencias/', views.IncidenciaListView.as_view(), name='incidencia_lista'),
    path('incidencias/nueva/', views.IncidenciaCreateView.as_view(), name='incidencia_crear'),
    path('incidencias/<int:pk>/', views.IncidenciaDetailView.as_view(), name='incidencia_detalle'),
    path('incidencias/<int:pk>/editar/', views.IncidenciaUpdateView.as_view(), name='incidencia_editar'),
    path('incidencias/<int:pk>/gestionar/', views.IncidenciaGestionView.as_view(), name='incidencia_gestionar'),
    path('incidencias/<int:pk>/eliminar/', views.IncidenciaDeleteView.as_view(), name='incidencia_eliminar'),
    path('incidencias/<int:pk>/comentar/', views.ComentarioCreateView.as_view(), name='incidencia_comentar'),

    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
]
