"""Contexto multi-edificio y contexto de seguridad para PostgreSQL RLS."""
from contextvars import ContextVar
from django.db import connection
from django.db.models import Q

_edificio_activo = ContextVar('edificio_activo', default=None)

def edificio_actual():
    return _edificio_activo.get()

class ContextoEdificioMiddleware:
    """Fija el edificio autorizado antes de ejecutar vistas y consultas."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .models import Edificio, Perfil, AuditoriaAcceso
        user = request.user
        edificio_id = None
        if user.is_authenticated:
            perfil = Perfil.objects.filter(usuario=user).only('edificio_id').first()
            solicitado = request.GET.get('edificio') or request.headers.get('X-Edificio-ID')
            es_privilegiado = user.is_superuser or user.groups.filter(name__in=['Administrador', 'Auditor', 'Técnico']).exists()
            if perfil and perfil.edificio_id and not es_privilegiado:
                edificio_id = perfil.edificio_id
            # Administradores/auditores/técnicos solo pueden activar edificios asociados.
            if solicitado and solicitado.isdigit():
                permitido = user.is_superuser or Edificio.objects.filter(pk=int(solicitado)).filter(
                    administradores=user
                ).exists() or Edificio.objects.filter(pk=int(solicitado), auditores=user).exists()
                permitido = permitido or Edificio.objects.filter(pk=int(solicitado), tecnicos__usuario=user, tecnicos__activo=True).exists()
                if permitido:
                    edificio_id = int(solicitado)
            elif es_privilegiado:
                # Selección inicial segura: primer edificio al que el usuario sí pertenece.
                permitidos = Edificio.objects.none()
                if user.is_superuser:
                    permitidos = Edificio.objects.all()
                else:
                    if user.groups.filter(name='Administrador').exists():
                        permitidos = permitidos | Edificio.objects.filter(administradores=user)
                    if user.groups.filter(name='Auditor').exists():
                        permitidos = permitidos | Edificio.objects.filter(auditores=user)
                    if user.groups.filter(name='Técnico').exists():
                        permitidos = permitidos | Edificio.objects.filter(tecnicos__usuario=user, tecnicos__activo=True)
                edificio_id = permitidos.order_by('pk').values_list('pk', flat=True).first()
        token = _edificio_activo.set(edificio_id)
        try:
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.current_building', %s, false)", [str(edificio_id or '')])
            response = self.get_response(request)
            # Audita accesos a rutas de incidencias sin guardar datos sensibles del cuerpo.
            if user.is_authenticated and request.path.startswith('/incidencias/'):
                ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
                AuditoriaAcceso.objects.create(usuario=user, edificio_id=edificio_id, ruta=request.path[:500], metodo=request.method, resultado=response.status_code, direccion_ip=ip or None)
            return response
        finally:
            if connection.vendor == 'postgresql':
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT set_config('app.current_building', '', false)")
                except Exception:
                    connection.close()
            _edificio_activo.reset(token)
