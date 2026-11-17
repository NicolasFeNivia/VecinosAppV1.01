from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from . import dominio, services
from .busqueda import buscar_incidencias
from .autorizacion import puede_realizar
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
    from .tenant import edificio_actual
    edificio_id = edificio_actual()
    if edificio_id is not None:
        qs = qs.filter(edificio_id=edificio_id)
    elif es_admin(user) or user.groups.filter(name__in=['Auditor', 'Técnico']).exists():
        return qs.none()
    if es_admin(user) or user.groups.filter(name='Auditor').exists():
        return qs
    if user.groups.filter(name='Técnico').exists():
        return qs.filter(tecnico__usuario=user, tecnico__activo=True)
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
        qs = incidencias_visibles(self.request.user).select_related('edificio', 'tecnico', 'residente')
        g = self.request.GET

        q = g.get('q', '').strip()
        if q:
            qs = buscar_incidencias(qs, q)
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
        ctx['puede_editar'] = puede_realizar(usuario, 'editar', incidencia)
        ctx['puede_eliminar'] = puede_realizar(usuario, 'eliminar', incidencia)
        ctx['eventos'] = incidencia.eventos.select_related('actor')
        ctx['puede_reabrir'] = dominio.puede_reabrir(incidencia.estado)
        return ctx


class IncidenciaCreateView(LoginRequiredMixin, CreateView):
    model = Incidencia
    form_class = IncidenciaForm

    def form_valid(self, form):
        perfil = getattr(self.request.user, 'perfil', None)
        if perfil is None or perfil.edificio is None:
            messages.error(self.request, 'Primero elige tu edificio en tu perfil.')
            return redirect('perfil')
        self.object = services.crear_incidencia(
            residente=self.request.user,
            edificio=perfil.edificio,
            **form.cleaned_data,
        )
        messages.success(self.request, 'Incidencia reportada correctamente.')
        return redirect(self.get_success_url())


class IncidenciaUpdateView(
    LoginRequiredMixin, RedirigirSinPermisoMixin, UserPassesTestMixin, UpdateView
):
    """El residente solo edita su incidencia mientras esté Pendiente."""

    model = Incidencia
    form_class = IncidenciaForm

    def get_queryset(self):
        return incidencias_visibles(self.request.user)

    def test_func(self):
        incidencia = self.get_object()
        return puede_realizar(self.request.user, 'editar', incidencia)

    def form_valid(self, form):
        messages.success(self.request, 'Incidencia actualizada.')
        return super().form_valid(form)


class IncidenciaGestionView(LoginRequiredMixin, AdminRequiredMixin, FormView):
    """Solo el administrador. Todo cambio pasa por el caso de uso `gestionar`."""

    form_class = IncidenciaGestionForm
    template_name = 'incidencias/incidencia_gestion.html'

    @cached_property
    def incidencia(self):
        return get_object_or_404(
            incidencias_visibles(self.request.user).select_related('edificio', 'tecnico'),
            pk=self.kwargs['pk']
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['incidencia'] = self.incidencia
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['object'] = self.incidencia
        return ctx

    def form_valid(self, form):
        try:
            services.gestionar(self.incidencia, actor=self.request.user, **form.cleaned_data)
        except dominio.DominioError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        messages.success(self.request, 'Incidencia gestionada correctamente.')
        return redirect('incidencia_detalle', pk=self.incidencia.pk)


class IncidenciaReabrirView(LoginRequiredMixin, AdminRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        incidencia = get_object_or_404(incidencias_visibles(request.user), pk=pk)
        try:
            services.reabrir(incidencia, actor=request.user, motivo=request.POST.get('motivo', ''))
            messages.success(request, 'Incidencia reabierta.')
        except dominio.DominioError as error:
            messages.error(request, str(error))
        return redirect('incidencia_detalle', pk=pk)


class IncidenciaDeleteView(
    LoginRequiredMixin, RedirigirSinPermisoMixin, UserPassesTestMixin, DeleteView
):
    """Solo el administrador o el dueño, con página de confirmación."""

    model = Incidencia
    success_url = reverse_lazy('incidencia_lista')

    def get_queryset(self):
        return incidencias_visibles(self.request.user)

    def test_func(self):
        incidencia = self.get_object()
        return puede_realizar(self.request.user, 'eliminar', incidencia)

    def form_valid(self, form):
        messages.success(self.request, 'Incidencia eliminada.')
        return super().form_valid(form)


# ---------- Comentarios ----------

class ComentarioCreateView(LoginRequiredMixin, View):
    """Recibe el comentario por POST desde la página de detalle."""

    http_method_names = ['post']

    def post(self, request, pk):
        incidencia = get_object_or_404(incidencias_visibles(request.user), pk=pk)
        if not puede_realizar(request.user, 'comentar', incidencia):
            return redirect('incidencia_lista')
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

        base = incidencias_visibles(self.request.user)
        por_categoria = {
            f['categoria']: f['total']
            for f in base.order_by().values('categoria').annotate(total=Count('id'))
        }
        por_estado = {
            f['estado']: f['total']
            for f in base.order_by().values('estado').annotate(total=Count('id'))
        }

        ctx['datos_categoria'] = {
            'labels': [etiqueta for _, etiqueta in Incidencia.CATEGORIAS],
            'values': [por_categoria.get(valor, 0) for valor, _ in Incidencia.CATEGORIAS],
        }
        ctx['datos_estado'] = {
            'labels': [etiqueta for _, etiqueta in Incidencia.ESTADOS],
            'values': [por_estado.get(valor, 0) for valor, _ in Incidencia.ESTADOS],
        }
        ctx['total'] = base.count()
        ctx['resumen_estados'] = [
            (etiqueta, por_estado.get(valor, 0)) for valor, etiqueta in Incidencia.ESTADOS
        ]
        return ctx
