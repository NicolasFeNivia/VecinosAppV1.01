from django.db import migrations


def calcular_pisos_y_unidades(apps, schema_editor):
    Unidad = apps.get_model('incidencias', 'Unidad')
    Perfil = apps.get_model('incidencias', 'Perfil')

    # Apartamentos que ya existían: 101 -> piso 1, 1203 -> piso 12
    for unidad in Unidad.objects.all():
        ident = (unidad.identificador or '').strip()
        if ident.isdigit() and len(ident) >= 3:
            Unidad.objects.filter(pk=unidad.pk).update(piso=int(ident[:-2]))

    # Perfiles que tenían "piso / puerta" en texto: se enlazan solo si coincide
    # exactamente con un apartamento de su edificio.
    for perfil in Perfil.objects.exclude(edificio__isnull=True):
        texto = (perfil.piso_puerta or '').strip()
        if not texto:
            continue
        unidad = Unidad.objects.filter(
            edificio_id=perfil.edificio_id, identificador=texto
        ).first()
        if unidad:
            Perfil.objects.filter(pk=perfil.pk).update(unidad=unidad)


class Migration(migrations.Migration):

    dependencies = [
        ('incidencias', '0005_unidad_piso_perfil_unidad'),
    ]

    operations = [
        migrations.RunPython(calcular_pisos_y_unidades, migrations.RunPython.noop),
    ]
