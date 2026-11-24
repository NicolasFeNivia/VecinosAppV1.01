from django.db import migrations

ORG = 'Organización por defecto'
SIN_EDIFICIO = 'Edificio sin asignar'


def texto_a_entidades(apps, schema_editor):
    Organizacion = apps.get_model('incidencias', 'Organizacion')
    Edificio = apps.get_model('incidencias', 'Edificio')
    Tecnico = apps.get_model('incidencias', 'Tecnico')
    Perfil = apps.get_model('incidencias', 'Perfil')
    Incidencia = apps.get_model('incidencias', 'Incidencia')

    org, _ = Organizacion.objects.get_or_create(nombre=ORG)
    sin_asignar, _ = Edificio.objects.get_or_create(organizacion=org, nombre=SIN_EDIFICIO)

    edificio_de_usuario = {}
    for perfil in Perfil.objects.all():
        nombre = (perfil.edificio_texto or '').strip()
        if nombre:
            edificio, _ = Edificio.objects.get_or_create(organizacion=org, nombre=nombre)
            Perfil.objects.filter(pk=perfil.pk).update(edificio=edificio)
            edificio_de_usuario[perfil.usuario_id] = edificio

    for inc in Incidencia.objects.all():
        edificio = edificio_de_usuario.get(inc.residente_id, sin_asignar)
        cambios = {'edificio': edificio}
        nombre_tecnico = (inc.tecnico_texto or '').strip()
        if nombre_tecnico:
            tecnico, _ = Tecnico.objects.get_or_create(nombre=nombre_tecnico)
            tecnico.edificios.add(edificio)
            cambios['tecnico'] = tecnico
        Incidencia.objects.filter(pk=inc.pk).update(**cambios)


def entidades_a_texto(apps, schema_editor):
    Perfil = apps.get_model('incidencias', 'Perfil')
    Incidencia = apps.get_model('incidencias', 'Incidencia')

    for perfil in Perfil.objects.select_related('edificio'):
        if perfil.edificio_id:
            Perfil.objects.filter(pk=perfil.pk).update(edificio_texto=perfil.edificio.nombre)
    for inc in Incidencia.objects.select_related('tecnico'):
        if inc.tecnico_id:
            Incidencia.objects.filter(pk=inc.pk).update(tecnico_texto=inc.tecnico.nombre)


class Migration(migrations.Migration):

    dependencies = [
        ('incidencias', '0002_dominio_multiedificio'),
    ]

    operations = [
        migrations.RunPython(texto_a_entidades, entidades_a_texto),
    ]
