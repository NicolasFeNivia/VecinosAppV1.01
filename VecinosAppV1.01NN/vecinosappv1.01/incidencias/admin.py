from django.contrib import admin

from .models import (
    AuditoriaAcceso, Comentario, Edificio, EventoIncidencia, Incidencia, Organizacion, Perfil, Tecnico, Unidad,
)


class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 0
    readonly_fields = ('creado',)


@admin.register(Incidencia)
class IncidenciaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'residente', 'edificio', 'categoria', 'prioridad', 'estado', 'tecnico', 'creada')
    list_filter = ('estado', 'edificio', 'categoria', 'prioridad', 'creada')
    search_fields = ('titulo', 'descripcion', 'residente__username', 'residente__email', 'tecnico__nombre')
    date_hierarchy = 'creada'
    # El estado solo cambia por los casos de uso, no desde el admin
    readonly_fields = ('creada', 'actualizada', 'estado')
    inlines = [ComentarioInline]


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'nombre_completo', 'piso_puerta', 'edificio')
    list_filter = ('edificio',)
    search_fields = ('usuario__username', 'nombre_completo', 'edificio__nombre')


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ('incidencia', 'autor', 'creado')
    list_filter = ('creado',)
    search_fields = ('texto', 'autor__username', 'incidencia__titulo')


@admin.register(Organizacion)
class OrganizacionAdmin(admin.ModelAdmin):
    search_fields = ('nombre',)


@admin.register(Edificio)
class EdificioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'organizacion', 'direccion')
    list_filter = ('organizacion',)
    search_fields = ('nombre',)
    filter_horizontal = ('administradores', 'auditores')


@admin.register(Unidad)
class UnidadAdmin(admin.ModelAdmin):
    list_display = ('identificador', 'edificio')
    list_filter = ('edificio',)


@admin.register(Tecnico)
class TecnicoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'usuario', 'activo')
    list_filter = ('activo',)
    filter_horizontal = ('edificios',)


@admin.register(EventoIncidencia)
class EventoIncidenciaAdmin(admin.ModelAdmin):
    list_display = ('incidencia', 'tipo', 'estado_anterior', 'estado_nuevo', 'actor', 'creado')
    list_filter = ('tipo',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaAcceso)
class AuditoriaAccesoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'edificio', 'metodo', 'ruta', 'resultado', 'creado')
    list_filter = ('metodo', 'resultado', 'edificio')
    search_fields = ('ruta', 'usuario__username')
    readonly_fields = ('usuario', 'edificio', 'ruta', 'metodo', 'resultado', 'direccion_ip', 'creado')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
