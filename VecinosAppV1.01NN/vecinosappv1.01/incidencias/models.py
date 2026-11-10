from django.conf import settings
from django.db import models
from django.urls import reverse


class Perfil(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil'
    )
    nombre_completo = models.CharField('Nombre completo', max_length=100, blank=True)
    piso_puerta = models.CharField('Piso / puerta', max_length=20, blank=True)
    edificio = models.CharField('Edificio', max_length=100, blank=True)

    class Meta:
        verbose_name_plural = 'perfiles'

    def __str__(self):
        return f'Perfil de {self.usuario.username}'


class Incidencia(models.Model):
    CATEGORIAS = [
        ('agua', 'Agua'),
        ('electricidad', 'Electricidad'),
        ('limpieza', 'Limpieza'),
        ('seguridad', 'Seguridad'),
        ('otros', 'Otros'),
    ]
    PRIORIDADES = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
    ]
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En Proceso'),
        ('resuelta', 'Resuelta'),
        ('cerrada', 'Cerrada'),
    ]

    titulo = models.CharField('Título', max_length=150)
    descripcion = models.TextField('Descripción')
    categoria = models.CharField('Categoría', max_length=20, choices=CATEGORIAS, default='otros')
    prioridad = models.CharField('Prioridad', max_length=10, choices=PRIORIDADES, default='media')
    estado = models.CharField('Estado', max_length=15, choices=ESTADOS, default='pendiente')
    foto = models.ImageField('Foto', upload_to='incidencias/', blank=True, null=True)
    residente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='incidencias'
    )
    tecnico = models.CharField('Técnico asignado', max_length=100, blank=True)
    notas_internas = models.TextField('Notas internas (solo administrador)', blank=True)
    creada = models.DateTimeField('Creada', auto_now_add=True)
    actualizada = models.DateTimeField('Actualizada', auto_now=True)

    class Meta:
        ordering = ['-creada']
        verbose_name = 'incidencia'
        verbose_name_plural = 'incidencias'

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return reverse('incidencia_detalle', args=[self.pk])

    @property
    def estado_badge(self):
        return {
            'pendiente': 'warning text-dark',
            'en_proceso': 'primary',
            'resuelta': 'success',
            'cerrada': 'secondary',
        }.get(self.estado, 'secondary')

    @property
    def prioridad_badge(self):
        return {'baja': 'info text-dark', 'media': 'warning text-dark', 'alta': 'danger'}.get(
            self.prioridad, 'secondary'
        )

    def delete(self, *args, **kwargs):
        # Borra también el archivo de la foto del disco
        if self.foto:
            self.foto.delete(save=False)
        super().delete(*args, **kwargs)


class Comentario(models.Model):
    incidencia = models.ForeignKey(
        Incidencia, on_delete=models.CASCADE, related_name='comentarios'
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comentarios'
    )
    texto = models.TextField('Comentario')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado']

    def __str__(self):
        return f'Comentario de {self.autor} en "{self.incidencia}"'
