from django.contrib import admin

from .models import Comentario, Incidencia, Perfil


class ComentarioInline(admin.TabularInline):
    model = Comentario
    extra = 0
    readonly_fields = ('creado',)


@admin.register(Incidencia)
class IncidenciaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'residente', 'categoria', 'prioridad', 'estado', 'tecnico', 'creada')
    list_filter = ('estado', 'categoria', 'prioridad', 'creada')
    search_fields = ('titulo', 'descripcion', 'residente__username', 'residente__email', 'tecnico')
    date_hierarchy = 'creada'
    readonly_fields = ('creada', 'actualizada')
    inlines = [ComentarioInline]


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'nombre_completo', 'piso_puerta', 'edificio')
    list_filter = ('edificio',)
    search_fields = ('usuario__username', 'nombre_completo', 'edificio')


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ('incidencia', 'autor', 'creado')
    list_filter = ('creado',)
    search_fields = ('texto', 'autor__username', 'incidencia__titulo')
