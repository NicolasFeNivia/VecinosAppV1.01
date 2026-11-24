from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.reverse import reverse

from eventos.models import WebhookEndpoint
from incidencias import services
from incidencias.models import Incidencia
from incidencias.views import incidencias_visibles

from .etag import exigir_if_match, respuesta_con_etag
from .idempotencia import ejecutar_idempotente
from .models import Adjunto
from .paginacion import PaginacionCursor
from .permisos import SoloAdministrador, puede_adjuntar, puede_cambiar_estado
from .serializers import (
    AdjuntoCrearSerializer,
    AdjuntoSerializer,
    AsignarSerializer,
    CambioEstadoSerializer,
    ComentarioSerializer,
    ErrorSerializer,
    IncidenciaCrearSerializer,
    IncidenciaSerializer,
    ReabrirSerializer,
    WebhookEndpointCreadoSerializer,
    WebhookEndpointSerializer,
)

IDEMPOTENCY_KEY = OpenApiParameter(
    'Idempotency-Key', OpenApiTypes.STR, OpenApiParameter.HEADER, required=False,
    description='Clave única (máx. 100 caracteres) para reintentar el POST sin duplicar el efecto. '
                'Si se repite con el mismo cuerpo se devuelve la respuesta original con la cabecera '
                '`Idempotent-Replayed: true`; con otro cuerpo, 422.',
)
IF_MATCH = OpenApiParameter(
    'If-Match', OpenApiTypes.STR, OpenApiParameter.HEADER, required=False,
    description='ETag leído en el GET. Si la incidencia cambió desde entonces, responde 412.',
)
IF_NONE_MATCH = OpenApiParameter(
    'If-None-Match', OpenApiTypes.STR, OpenApiParameter.HEADER, required=False,
    description='ETag que el cliente ya tiene; si no cambió, responde 304 sin cuerpo.',
)
ERRORES = {
    401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer,
    412: ErrorSerializer, 422: ErrorSerializer, 429: ErrorSerializer,
}


class IncidenciaViewSet(viewsets.GenericViewSet):
    """Incidencias visibles para el usuario autenticado (mismas reglas que la web)."""

    serializer_class = IncidenciaSerializer
    pagination_class = PaginacionCursor
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Incidencia.objects.none()
        qs = IncidenciaSerializer.optimizar(incidencias_visibles(self.request.user))
        if self.action == 'list':
            p = self.request.query_params
            for campo in ('estado', 'categoria', 'prioridad'):
                if p.get(campo):
                    qs = qs.filter(**{campo: p[campo]})
            if p.get('q'):
                qs = qs.filter(titulo__icontains=p['q'])
        return qs

    # ----- utilidades -----

    def _datos(self, incidencia):
        """Representación actual (releída con el queryset optimizado)."""
        incidencia = self.get_queryset().get(pk=incidencia.pk)
        return IncidenciaSerializer(incidencia, context={'request': self.request}).data

    def _idempotente(self, request, funcion):
        def ejecutar():
            try:
                return funcion(request)
            except Exception as exc:
                return self.handle_exception(exc)

        return ejecutar_idempotente(request, ejecutar)

    # ----- lectura -----

    @extend_schema(
        parameters=[
            OpenApiParameter('estado', OpenApiTypes.STR, enum=[e for e, _ in Incidencia.ESTADOS]),
            OpenApiParameter('categoria', OpenApiTypes.STR, enum=[c for c, _ in Incidencia.CATEGORIAS]),
            OpenApiParameter('prioridad', OpenApiTypes.STR, enum=[p for p, _ in Incidencia.PRIORIDADES]),
            OpenApiParameter('q', OpenApiTypes.STR, description='Busca en el título.'),
            IF_NONE_MATCH,
        ],
        responses={200: IncidenciaSerializer(many=True), 304: None, **ERRORES},
        summary='Lista incidencias (paginación por cursor)',
    )
    def list(self, request):
        pagina = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        serializador = self.get_serializer(pagina, many=True)
        respuesta = self.get_paginated_response(serializador.data)
        return respuesta_con_etag(request, respuesta.data)

    @extend_schema(
        parameters=[IF_NONE_MATCH],
        responses={200: IncidenciaSerializer, 304: None, **ERRORES},
        summary='Detalle de una incidencia (con ETag)',
    )
    def retrieve(self, request, pk=None):
        return respuesta_con_etag(request, self._datos(self.get_object()))

    # ----- creación -----

    @extend_schema(
        request=IncidenciaCrearSerializer,
        parameters=[IDEMPOTENCY_KEY],
        responses={201: IncidenciaSerializer, 400: ErrorSerializer, **ERRORES},
        summary='Reporta una incidencia',
    )
    def create(self, request):
        return self._idempotente(request, self._crear)

    def _crear(self, request):
        serializador = IncidenciaCrearSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        perfil = getattr(request.user, 'perfil', None)
        if perfil is None or perfil.edificio_id is None:
            raise PermissionDenied('Tu cuenta no tiene un edificio asignado.')
        datos = dict(serializador.validated_data)
        incidencia = services.crear_incidencia(
            residente=request.user,
            edificio=perfil.edificio,
            unidad=perfil.unidad,
            foto=datos.pop('foto', None),
            **datos,
        )
        return Response(
            self._datos(incidencia),
            status=status.HTTP_201_CREATED,
            headers={'Location': reverse('api:incidencia-detail', args=[incidencia.pk], request=request)},
        )

    # ----- casos de uso de M1 -----

    @extend_schema(
        request=CambioEstadoSerializer,
        parameters=[IDEMPOTENCY_KEY, IF_MATCH],
        responses={200: IncidenciaSerializer, **ERRORES},
        summary='Cambia el estado (administrador o técnico asignado)',
    )
    @action(detail=True, methods=['post'], url_path='estado')
    def estado(self, request, pk=None):
        return self._idempotente(request, self._estado)

    def _estado(self, request):
        incidencia = self.get_object()
        if not puede_cambiar_estado(request.user, incidencia):
            raise PermissionDenied('No puedes cambiar el estado de esta incidencia.')
        exigir_if_match(request, self._datos(incidencia))
        serializador = CambioEstadoSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        nuevo = serializador.validated_data['estado']
        if nuevo != incidencia.estado:
            services.cambiar_estado(incidencia, nuevo, actor=request.user)
        return Response(self._datos(incidencia))

    @extend_schema(
        request=ReabrirSerializer,
        parameters=[IDEMPOTENCY_KEY, IF_MATCH],
        responses={200: IncidenciaSerializer, **ERRORES},
        summary='Reabre una incidencia resuelta o cerrada (administrador)',
    )
    @action(detail=True, methods=['post'], url_path='reabrir', permission_classes=[SoloAdministrador])
    def reabrir(self, request, pk=None):
        return self._idempotente(request, self._reabrir)

    def _reabrir(self, request):
        incidencia = self.get_object()
        exigir_if_match(request, self._datos(incidencia))
        serializador = ReabrirSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        services.reabrir(incidencia, actor=request.user, motivo=serializador.validated_data['motivo'])
        return Response(self._datos(incidencia))

    @extend_schema(
        request=AsignarSerializer,
        parameters=[IDEMPOTENCY_KEY, IF_MATCH],
        responses={200: IncidenciaSerializer, **ERRORES},
        summary='Asigna o quita el técnico (administrador)',
    )
    @action(detail=True, methods=['post'], url_path='asignar', permission_classes=[SoloAdministrador])
    def asignar(self, request, pk=None):
        return self._idempotente(request, self._asignar)

    def _asignar(self, request):
        incidencia = self.get_object()
        exigir_if_match(request, self._datos(incidencia))
        serializador = AsignarSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        services.asignar_tecnico(incidencia, serializador.validated_data['tecnico'], actor=request.user)
        return Response(self._datos(incidencia))

    # ----- comentarios -----

    @extend_schema(responses={200: ComentarioSerializer(many=True), **ERRORES}, summary='Lista los comentarios')
    @action(detail=True, methods=['get'], url_path='comentarios')
    def comentarios(self, request, pk=None):
        incidencia = self.get_object()
        serializador = ComentarioSerializer(incidencia.comentarios.select_related('autor'), many=True)
        return Response(serializador.data)

    @extend_schema(
        request=ComentarioSerializer,
        parameters=[IDEMPOTENCY_KEY],
        responses={201: ComentarioSerializer, **ERRORES},
        summary='Agrega un comentario',
    )
    @comentarios.mapping.post
    def crear_comentario(self, request, pk=None):
        return self._idempotente(request, self._comentar)

    def _comentar(self, request):
        incidencia = self.get_object()
        serializador = ComentarioSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        comentario = serializador.save(incidencia=incidencia, autor=request.user)
        return Response(ComentarioSerializer(comentario).data, status=status.HTTP_201_CREATED)

    # ----- adjuntos -----

    @extend_schema(responses={200: AdjuntoSerializer(many=True), **ERRORES}, summary='Lista los adjuntos')
    @action(detail=True, methods=['get'], url_path='adjuntos')
    def adjuntos(self, request, pk=None):
        incidencia = self.get_object()
        serializador = AdjuntoSerializer(
            incidencia.adjuntos.all(), many=True, context={'request': request}
        )
        return Response(serializador.data)

    @extend_schema(
        request={'multipart/form-data': AdjuntoCrearSerializer},
        parameters=[IDEMPOTENCY_KEY],
        responses={201: AdjuntoSerializer, 400: ErrorSerializer, **ERRORES},
        summary='Sube un adjunto (imagen o PDF; se verifica el contenido real)',
    )
    @adjuntos.mapping.post
    def subir_adjunto(self, request, pk=None):
        return self._idempotente(request, self._adjuntar)

    def _adjuntar(self, request):
        incidencia = self.get_object()
        if not puede_adjuntar(request.user, incidencia):
            raise PermissionDenied('No puedes adjuntar archivos a esta incidencia.')
        serializador = AdjuntoCrearSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        archivo = serializador.validated_data['archivo']
        adjunto = Adjunto.objects.create(
            incidencia=incidencia,
            subido_por=request.user,
            archivo=archivo,
            nombre_original=archivo.name[:255],
            tipo_contenido=archivo.content_type,
            tamano=archivo.size,
        )
        return Response(
            AdjuntoSerializer(adjunto, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(responses=ERRORES)
class WebhookViewSet(viewsets.ModelViewSet):
    """Endpoints que reciben eventos firmados (HMAC-SHA256 + marca de tiempo). Solo administrador."""

    queryset = WebhookEndpoint.objects.select_related('edificio').order_by('id')
    permission_classes = [permissions.IsAuthenticated, SoloAdministrador]
    pagination_class = None
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return WebhookEndpointCreadoSerializer
        return WebhookEndpointSerializer
