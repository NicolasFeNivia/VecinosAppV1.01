from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import UploadedFile

from .models import Comentario, Incidencia, Perfil

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
    edificio = forms.CharField(label='Edificio', max_length=100)

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


class IncidenciaGestionForm(BootstrapMixin, forms.ModelForm):
    """Formulario del administrador: estado, prioridad, técnico y notas internas."""

    class Meta:
        model = Incidencia
        fields = ['estado', 'prioridad', 'tecnico', 'notas_internas']
        widgets = {'notas_internas': forms.Textarea(attrs={'rows': 4})}


class ComentarioForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Comentario
        fields = ['texto']
        labels = {'texto': 'Escribe un comentario'}
        widgets = {'texto': forms.Textarea(attrs={'rows': 3})}
