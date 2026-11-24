import re
from collections import defaultdict

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import UploadedFile

from . import dominio
from .models import Comentario, Edificio, Incidencia, Perfil, Tecnico, Unidad

User = get_user_model()

MAX_FOTO_MB = 2


class BootstrapMixin:
    """Agrega las clases de Bootstrap 5 a todos los campos del formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                clase = 'form-check-input'
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                clase = 'form-select'
            else:
                clase = 'form-control'
            widget.attrs['class'] = (widget.attrs.get('class', '') + ' ' + clase).strip()


class LoginForm(BootstrapMixin, AuthenticationForm):
    pass


def _natural(texto):
    """Orden natural: 2 antes que 10, 101 antes que 102."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', texto)]


def edificios_con_apartamentos():
    """Solo se pueden elegir edificios que ya tienen apartamentos cargados."""
    return Edificio.objects.filter(unidades__isnull=False).distinct().order_by('nombre')


def datos_vivienda():
    """Árbol edificio -> piso -> apartamentos que usa el selector en cascada."""
    edificios = list(edificios_con_apartamentos())
    por_edificio = defaultdict(lambda: defaultdict(list))
    for unidad in Unidad.objects.filter(edificio__in=edificios):
        por_edificio[unidad.edificio_id][unidad.piso].append(unidad)

    datos = []
    for edificio in edificios:
        pisos = []
        for numero in sorted(por_edificio[edificio.pk]):
            unidades = sorted(
                por_edificio[edificio.pk][numero], key=lambda u: _natural(u.identificador)
            )
            pisos.append({
                'numero': numero,
                'etiqueta': f'Piso {numero}: ' + ', '.join(u.identificador for u in unidades),
                'unidades': [{'id': u.pk, 'nombre': u.identificador} for u in unidades],
            })
        datos.append({'id': edificio.pk, 'nombre': edificio.nombre, 'pisos': pisos})
    return datos


class RegistroForm(BootstrapMixin, UserCreationForm):
    """Edificio, piso y apartamento se eligen de listas (nunca se escriben)."""

    email = forms.EmailField(label='Correo electrónico', required=True)
    nombre_completo = forms.CharField(label='Nombre completo', max_length=100)
    edificio = forms.ModelChoiceField(
        queryset=Edificio.objects.none(),
        label='Edificio',
        empty_label='Selecciona tu edificio',
    )
    # Las opciones de piso y apartamento las llena el navegador según el edificio
    # elegido; el servidor vuelve a validar la combinación completa en clean().
    piso = forms.IntegerField(
        label='Piso',
        min_value=0,
        widget=forms.Select(choices=[('', 'Selecciona tu piso')]),
    )
    unidad = forms.ModelChoiceField(
        queryset=Unidad.objects.none(),
        label='Apartamento',
        empty_label='Selecciona tu apartamento',
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        edificios = edificios_con_apartamentos()
        self.fields['edificio'].queryset = edificios
        self.fields['unidad'].queryset = Unidad.objects.filter(edificio__in=edificios)
        # Solo el marcador: el navegador agrega los apartamentos del piso elegido
        self.fields['unidad'].widget.choices = [('', 'Selecciona tu apartamento')]
        self.datos_vivienda = datos_vivienda()

    @property
    def seleccion_inicial(self):
        """Lo que la persona ya había elegido (para no perderlo si hay errores)."""
        return {
            nombre: self.data.get(self.add_prefix(nombre), '') if self.is_bound else ''
            for nombre in ('edificio', 'piso', 'unidad')
        }

    def campos(self, *nombres):
        return [self[nombre] for nombre in nombres]

    @property
    def campos_datos(self):
        return self.campos('username', 'email', 'nombre_completo')

    @property
    def campos_vivienda(self):
        return self.campos('edificio', 'piso', 'unidad')

    @property
    def campos_clave(self):
        return self.campos('password1', 'password2')

    def clean(self):
        datos = super().clean()
        edificio = datos.get('edificio')
        piso = datos.get('piso')
        unidad = datos.get('unidad')
        if unidad is not None:
            if edificio is not None and unidad.edificio_id != edificio.pk:
                self.add_error('unidad', 'Ese apartamento no pertenece al edificio elegido.')
            elif piso is not None and unidad.piso != piso:
                self.add_error('unidad', 'Ese apartamento no está en el piso elegido.')
        return datos

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            # Todo usuario nuevo entra al grupo "Residente"
            grupo, _ = Group.objects.get_or_create(name='Residente')
            user.groups.add(grupo)
            perfil, _ = Perfil.objects.get_or_create(usuario=user)
            perfil.nombre_completo = self.cleaned_data['nombre_completo']
            perfil.unidad = self.cleaned_data['unidad']
            perfil.edificio = self.cleaned_data['edificio']
            perfil.save()
        return user


class PerfilForm(BootstrapMixin, forms.ModelForm):
    """El residente solo cambia su nombre; el edificio y el apartamento los
    asigna el administrador (así cada usuario ve solo su edificio)."""

    class Meta:
        model = Perfil
        fields = ['nombre_completo']


class IncidenciaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Incidencia
        fields = ['titulo', 'descripcion', 'categoria', 'prioridad', 'foto']
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 4})}
        help_texts = {
            'titulo': 'Mínimo 10 caracteres.',
            'foto': f'Opcional. Máximo {MAX_FOTO_MB} MB.',
        }

    def clean_titulo(self):
        titulo = self.cleaned_data['titulo'].strip()
        if len(titulo) < 10:
            raise forms.ValidationError('El título debe tener al menos 10 caracteres.')
        return titulo

    def clean_foto(self):
        foto = self.cleaned_data.get('foto')
        # Solo se valida cuando se está subiendo un archivo nuevo
        if isinstance(foto, UploadedFile) and foto.size > MAX_FOTO_MB * 1024 * 1024:
            raise forms.ValidationError(f'La foto no puede pesar más de {MAX_FOTO_MB} MB.')
        return foto


class IncidenciaGestionForm(BootstrapMixin, forms.Form):
    """Estado, prioridad, técnico y notas. Solo ofrece transiciones válidas."""

    estado = forms.ChoiceField(label='Estado', choices=[])
    prioridad = forms.ChoiceField(label='Prioridad', choices=Incidencia.PRIORIDADES)
    tecnico = forms.ModelChoiceField(
        label='Técnico asignado',
        queryset=Tecnico.objects.none(),
        required=False,
        empty_label='Sin técnico',
    )
    notas_internas = forms.CharField(
        label='Notas internas (solo administrador)',
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
    )

    def __init__(self, *args, incidencia, **kwargs):
        kwargs['initial'] = {
            'estado': incidencia.estado,
            'prioridad': incidencia.prioridad,
            'tecnico': incidencia.tecnico_id,
            'notas_internas': incidencia.notas_internas,
            **kwargs.get('initial', {}),
        }
        super().__init__(*args, **kwargs)
        self.incidencia = incidencia
        etiquetas = dict(Incidencia.ESTADOS)
        self.fields['estado'].choices = [
            (incidencia.estado, f'{etiquetas[incidencia.estado]} (actual)')
        ] + [
            (valor, etiqueta)
            for valor, etiqueta in Incidencia.ESTADOS
            if dominio.puede_pasar(incidencia.estado, valor)
        ]
        self.fields['tecnico'].queryset = Tecnico.objects.filter(
            edificios=incidencia.edificio_id, activo=True
        )


class IncidenciaEstadoForm(BootstrapMixin, forms.Form):
    """Lo único que puede hacer un reparador: avanzar el estado de su incidencia.

    Solo ofrece transiciones válidas y nunca 'Cerrada' (eso lo decide el administrador).
    """

    estado = forms.ChoiceField(label='Estado', choices=[])

    def __init__(self, *args, incidencia, **kwargs):
        kwargs['initial'] = {'estado': incidencia.estado, **kwargs.get('initial', {})}
        super().__init__(*args, **kwargs)
        self.incidencia = incidencia
        etiquetas = dict(Incidencia.ESTADOS)
        self.fields['estado'].choices = [
            (incidencia.estado, f'{etiquetas[incidencia.estado]} (actual)')
        ] + [
            (valor, etiqueta)
            for valor, etiqueta in Incidencia.ESTADOS
            if valor != dominio.CERRADA and dominio.puede_pasar(incidencia.estado, valor)
        ]

    @staticmethod
    def hay_cambios_posibles(incidencia):
        return any(
            valor != dominio.CERRADA and dominio.puede_pasar(incidencia.estado, valor)
            for valor, _ in Incidencia.ESTADOS
        )


class ComentarioForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['texto']
        labels = {'texto': 'Escribe un comentario'}
        widgets = {'texto': forms.Textarea(attrs={'rows': 3})}
