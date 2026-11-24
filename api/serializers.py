import secrets
from urllib.parse import urlparse

from django.db.models import Count
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from PIL import Image
from rest_framework import serializers

from eventos.models import WebhookEndpoint
from eventos.servicios import EVENTOS_VALIDOS
from incidencias.models import Comentario, Edificio, Incidencia, Tecnico, Unidad

from .models import Adjunto

MAX_ADJUNTO_MB = 5
FORMATOS_IMAGEN = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'WEBP': 'image/webp',
    'GIF': 'image/gif',
}


class ErrorSerializer(serializers.Serializer):
    codigo = serializers.CharField()
    detalle = serializers.CharField()


class EdificioMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edificio
        fields = ['id', 'nombre']


class UnidadMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unidad
        fields = ['id', 'piso', 'identificador']


class TecnicoMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tecnico
        fields = ['id', 'nombre']


class AdjuntoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Adjunto
        fields = ['id', 'archivo', 'nombre_original', 'tipo_contenido', 'tamano', 'creado']
        read_only_fields = fields


class AdjuntoCrearSerializer(serializers.Serializer):
    archivo = serializers.FileField()

    def validate_archivo(self, archivo):
        """Verifica el contenido REAL (firma del archivo), no la extensión ni el Content-Type."""
        if archivo.size > MAX_ADJUNTO_MB * 1024 * 1024:
            raise serializers.ValidationError(f'El archivo no puede pesar más de {MAX_ADJUNTO_MB} MB.')
        cabecera = archivo.read(8)
        archivo.seek(0)
        if cabecera.startswith(b'%PDF-'):
            tipo = 'application/pdf'
        else:
            try:
                imagen = Image.open(archivo)
                formato = imagen.format
                imagen.verify()
            except Exception:
                raise serializers.ValidationError('El archivo no es una imagen ni un PDF válido.')
            finally:
                archivo.seek(0)
            if formato not in FORMATOS_IMAGEN:
                raise serializers.ValidationError('Formato no permitido. Usa JPEG, PNG, WEBP, GIF o PDF.')
            tipo = FORMATOS_IMAGEN[formato]
        archivo.content_type = tipo
        return archivo


class ComentarioSerializer(serializers.ModelSerializer):
    autor = serializers.CharField(source='autor.username', read_only=True)

    class Meta:
        model = Comentario
        fields = ['id', 'autor', 'texto', 'creado']
        read_only_fields = ['id', 'autor', 'creado']

    def validate_texto(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError('El comentario no puede estar vacío.')
        return valor


class IncidenciaSerializer(serializers.ModelSerializer):
    residente = serializers.CharField(source='residente.username', read_only=True)
    edificio = EdificioMiniSerializer(read_only=True)
    unidad = UnidadMiniSerializer(read_only=True)
    tecnico = TecnicoMiniSerializer(read_only=True)
    adjuntos = AdjuntoSerializer(many=True, read_only=True)
    total_comentarios = serializers.SerializerMethodField()

    class Meta:
        model = Incidencia
        fields = [
            'id', 'titulo', 'descripcion', 'categoria', 'prioridad', 'estado', 'foto',
            'residente', 'edificio', 'unidad', 'tecnico', 'adjuntos', 'total_comentarios',
            'creada', 'actualizada',
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.INT)
    def get_total_comentarios(self, obj):
        valor = getattr(obj, 'total_comentarios', None)
        return obj.comentarios.count() if valor is None else valor

    @staticmethod
    def optimizar(queryset):
        """Evita N+1: todo lo que el serializador toca se carga en pocas consultas."""
        return queryset.select_related(
            'residente', 'edificio', 'unidad', 'tecnico'
        ).prefetch_related('adjuntos').annotate(total_comentarios=Count('comentarios', distinct=True))


class IncidenciaCrearSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=150)
    descripcion = serializers.CharField()
    categoria = serializers.ChoiceField(choices=Incidencia.CATEGORIAS, default='otros')
    prioridad = serializers.ChoiceField(choices=Incidencia.PRIORIDADES, default='media')
    foto = serializers.ImageField(required=False, allow_null=True)

    def validate_titulo(self, valor):
        valor = valor.strip()
        if len(valor) < 10:
            raise serializers.ValidationError('El título debe tener al menos 10 caracteres.')
        return valor


class CambioEstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Incidencia.ESTADOS)


class ReabrirSerializer(serializers.Serializer):
    motivo = serializers.CharField()


class AsignarSerializer(serializers.Serializer):
    tecnico = serializers.PrimaryKeyRelatedField(
        queryset=Tecnico.objects.all(), allow_null=True,
        help_text='ID del técnico, o null para quitar la asignación.',
    )


class WebhookEndpointSerializer(serializers.ModelSerializer):
    edificio = serializers.PrimaryKeyRelatedField(queryset=Edificio.objects.all())
    eventos = serializers.ListField(
        child=serializers.ChoiceField(choices=EVENTOS_VALIDOS), required=False, allow_empty=False
    )

    class Meta:
        model = WebhookEndpoint
        fields = ['id', 'edificio', 'url', 'eventos', 'activo', 'creado']
        read_only_fields = ['id', 'creado']

    def validate_url(self, valor):
        if urlparse(valor).scheme not in ('http', 'https'):
            raise serializers.ValidationError('Solo se permiten URLs http o https.')
        return valor


class WebhookEndpointCreadoSerializer(WebhookEndpointSerializer):
    """Solo en la creación: el secreto se muestra una única vez."""

    secreto = serializers.CharField(read_only=True)

    class Meta(WebhookEndpointSerializer.Meta):
        fields = WebhookEndpointSerializer.Meta.fields + ['secreto']
        read_only_fields = WebhookEndpointSerializer.Meta.read_only_fields + ['secreto']

    def create(self, validated_data):
        validated_data['secreto'] = secrets.token_urlsafe(32)
        return super().create(validated_data)
