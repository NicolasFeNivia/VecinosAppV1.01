from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Incidencia, Perfil

User = get_user_model()


@receiver(post_save, sender=User)
def crear_perfil(sender, instance, created, **kwargs):
    """Cada usuario nuevo recibe su perfil vacío."""
    if created:
        Perfil.objects.get_or_create(usuario=instance)


@receiver(pre_save, sender=Incidencia)
def guardar_estado_anterior(sender, instance, **kwargs):
    """Guarda el estado que tenía la incidencia antes de este guardado."""
    if instance.pk:
        instance._estado_anterior = (
            Incidencia.objects.filter(pk=instance.pk).values_list('estado', flat=True).first()
        )
    else:
        instance._estado_anterior = None


@receiver(post_save, sender=Incidencia)
def avisar_incidencia_resuelta(sender, instance, created, **kwargs):
    """Bonus: correo al residente cuando su incidencia pasa a 'Resuelta'."""
    anterior = getattr(instance, '_estado_anterior', None)
    if created or instance.estado != 'resuelta' or anterior == 'resuelta':
        return
    correo = instance.residente.email
    if not correo:
        return
    send_mail(
        subject=f'Tu incidencia "{instance.titulo}" fue resuelta',
        message=(
            f'Hola {instance.residente.username},\n\n'
            f'Tu incidencia "{instance.titulo}" cambió su estado a Resuelta.\n'
            'Si todo está bien, no necesitas hacer nada más.\n\n'
            'VecinosApp'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[correo],
        fail_silently=True,
    )
