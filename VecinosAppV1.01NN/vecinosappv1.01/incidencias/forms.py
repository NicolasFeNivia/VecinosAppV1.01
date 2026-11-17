from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import UploadedFile

from . import dominio
from .models import Comentario, Edificio, Incidencia, Perfil, Tecnico

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


class RegistroForm(BootstrapMixin, UserCreationForm):
    email = forms.EmailField(label='Correo electrónico', required=True)
    nombre_completo = forms.CharField(label='Nombre completo', max_length=100)
    piso_puerta = forms.CharField(label='Piso / puerta', max_length=20)
    edificio = forms.ModelChoiceField(queryset=Edificio.objects.all(), label='Edificio')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

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
            perfil.piso_puerta = self.cleaned_data['piso_puerta']
            perfil.edificio = self.cleaned_data['edificio']
            perfil.save()
        return user


class PerfilForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Perfil
        fields = ['nombre_completo', 'piso_puerta', 'edificio']


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


class ComentarioForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['texto']
        labels = {'texto': 'Escribe un comentario'}
        widgets = {'texto': forms.Textarea(attrs={'rows': 3})}
