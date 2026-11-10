from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import (
    ComentarioForm,
    IncidenciaForm,
    IncidenciaGestionForm,
    PerfilForm,
    RegistroForm,
)
from .mixins import AdminRequiredMixin, RedirigirSinPermisoMixin, es_admin
from .models import Incidencia, Perfil


def incidencias_visibles(user):
    """El administrador ve todas; el residente solo las suyas."""
    qs = Incidencia.objects.select_related('residente')
    if es_admin(user):
        return qs
    return qs.filter(residente=user)


def _fecha(valor):
    try:
        return parse_date(valor or '')
    except ValueError:
        return None


# ---------- Páginas y cuentas ----------

class InicioView(TemplateView):
    template_name = 'incidencias/inicio.html'


class RegistroView(CreateView):
    form_class = RegistroForm
    template_name = 'incidencias/registro.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(self.request, 'Cuenta creada. Ya puedes iniciar sesión.')
        return respuesta


class PerfilUpdateView(LoginRequiredMixin, UpdateView):
    form_class = PerfilForm
    template_name = 'incidencias/perfil.html'
    success_url = reverse_lazy('perfil')

    def get_object(self, queryset=None):
        perfil, _ = Perfil.objects.get_or_create(usuario=self.request.user)
        return perfil

    def form_valid(self, form):
        messages.success(self.request, 'Perfil actualizado.')
        return super().form_valid(form)


# ---------- CRUD de incidencias ----------

class IncidenciaListView(LoginRequiredMixin, ListView):
    model = Incidencia
    paginate_by = 10  # Bonus: paginación

    def get_queryset(self):
        qs = incidencias_visibles(self.request.user)
        g = self.request.GET

        q = g.get('q', '').strip()
        if q:
            qs = qs.filter(Q(titulo__icontains=q) | Q(descripcion__icontains=q))
        if g.get('categoria'):
            qs = qs.filter(categoria=g['categoria'])
        if g.get('estado'):
            qs = qs.filter(estado=g['estado'])
        desde = _fecha(g.get('desde'))
        if desde:
            qs = qs.filter(creada__date__gte=desde)
        hasta = _fecha(g.get('hasta'))
        if hasta:
            qs = qs.filter(creada__date__lte=hasta)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categorias'] = Incidencia.CATEGORIAS
        ctx['estados'] = Incidencia.ESTADOS
        params = self.request.GET.copy()
        params.pop('page', None)
        ctx['querystring'] = params.urlencode()
        return ctx


class IncidenciaDetailView(LoginRequiredMixin, DetailView):
    model = Incidencia

    def get_queryset(self):
        return incidencias_visibles(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        incidencia = self.object
        usuario = self.request.user
        ctx['comentarios'] = incidencia.comentarios.select_related('autor')
        ctx['comentario_form'] = ComentarioForm()
        ctx['puede_editar'] = incidencia.residente == usuario and incidencia.estado == 'pendiente'
        ctx['puede_eliminar'] = es_admin(usuario) or incidencia.residente == usuario
        return ctx


class IncidenciaCreateView(LoginRequiredMixin, CreateView):
    model = Incidencia
    form_class = IncidenciaForm

    def form_valid(self, form):
        form.instance.residente = self.request.user
        messages.success(self.request, 'Incidencia reportada correctamente.')
        return super().form_valid(form)


class IncidenciaUpdateView(
    LoginRequiredMixin, RedirigirSinPermisoMixin, UserPassesTestMixin, UpdateView
):
    """El residente solo edita su incidencia mientras esté Pendiente."""

    model = Incidencia
    form_class = IncidenciaForm

    def test_func(self):
        incidencia = self.get_object()
        return incidencia.residente == self.request.user and incidencia.estado == 'pendiente'

    def form_valid(self, form):
        messages.success(self.request, 'Incidencia actualizada.')
        return super().form_valid(form)


class IncidenciaGestionView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Solo el administrador: cambia estado, prioridad, técnico y notas internas."""

    model = Incidencia
    form_class = IncidenciaGestionForm
    template_name = 'incidencias/incidencia_gestion.html'

    def get_success_url(self):
        return reverse('incidencia_detalle', args=[self.object.pk])

    def form_valid(self, form):
        messages.success(self.request, 'Incidencia gestionada correctamente.')
        return super().form_valid(form)


class IncidenciaDeleteView(
    LoginRequiredMixin, RedirigirSinPermisoMixin, UserPassesTestMixin, DeleteView
):
    """Solo el administrador o el dueño, con página de confirmación."""

    model = Incidencia
    success_url = reverse_lazy('incidencia_lista')

    def test_func(self):
        incidencia = self.get_object()
        return es_admin(self.request.user) or incidencia.residente == self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Incidencia eliminada.')
        return super().form_valid(form)


# ---------- Comentarios ----------

class ComentarioCreateView(LoginRequiredMixin, View):
    """Recibe el comentario por POST desde la página de detalle."""

    http_method_names = ['post']

    def post(self, request, pk):
        incidencia = get_object_or_404(incidencias_visibles(request.user), pk=pk)
        form = ComentarioForm(request.POST)
        if form.is_valid():
            comentario = form.save(commit=False)
            comentario.incidencia = incidencia
            comentario.autor = request.user
            comentario.save()
            messages.success(request, 'Comentario agregado.')
        else:
            messages.error(request, 'El comentario no puede estar vacío.')
        return redirect('incidencia_detalle', pk=pk)


# ---------- Dashboard (Bonus) ----------

class DashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = 'incidencias/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        por_categoria = {
            f['categoria']: f['total']
            for f in Incidencia.objects.order_by().values('categoria').annotate(total=Count('id'))
        }
        por_estado = {
            f['estado']: f['total']
            for f in Incidencia.objects.order_by().values('estado').annotate(total=Count('id'))
        }

        ctx['datos_categoria'] = {
            'labels': [etiqueta for _, etiqueta in Incidencia.CATEGORIAS],
            'values': [por_categoria.get(valor, 0) for valor, _ in Incidencia.CATEGORIAS],
        }
        ctx['datos_estado'] = {
            'labels': [etiqueta for _, etiqueta in Incidencia.ESTADOS],
            'values': [por_estado.get(valor, 0) for valor, _ in Incidencia.ESTADOS],
        }
        ctx['total'] = Incidencia.objects.count()
        ctx['resumen_estados'] = [
            (etiqueta, por_estado.get(valor, 0)) for valor, etiqueta in Incidencia.ESTADOS
        ]
        return ctx
