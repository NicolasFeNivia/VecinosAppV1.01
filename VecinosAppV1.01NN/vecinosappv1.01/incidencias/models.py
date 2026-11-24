from django.conf import settings
from django.db import models
from django.urls import reverse


class Organizacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = 'organización'
        verbose_name_plural = 'organizaciones'

    def __str__(self):
        return self.nombre


class Edificio(models.Model):
    organizacion = models.ForeignKey(
        Organizacion, on_delete=models.PROTECT, related_name='edificios'
    )
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200, blank=True)
    administradores = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='edificios_administrados'
    )
    auditores = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='edificios_auditados'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['organizacion', 'nombre'], name='edificio_unico_por_organizacion'
            )
        ]

    def __str__(self):
        return self.nombre


class Unidad(models.Model):
    edificio = models.ForeignKey(Edificio, on_delete=models.CASCADE, related_name='unidades')
    identificador = models.CharField(max_length=20)

    class Meta:
        verbose_name = 'unidad'
        verbose_name_plural = 'unidades'
        constraints = [
            models.UniqueConstraint(
                fields=['edificio', 'identificador'], name='unidad_unica_por_edificio'
            )
        ]

    def __str__(self):
        return f'{self.edificio} - {self.identificador}'


class Tecnico(models.Model):
    nombre = models.CharField(max_length=100)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tecnico',
    )
    edificios = models.ManyToManyField(Edificio, blank=True, related_name='tecnicos')
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


class Perfil(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil'
    )
    nombre_completo = models.CharField('Nombre completo', max_length=100, blank=True)
    piso_puerta = models.CharField('Piso / puerta', max_length=20, blank=True)
    edificio = models.ForeignKey(
        Edificio,
        verbose_name='Edificio',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='residentes',
    )

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
    edificio = models.ForeignKey(
        Edificio, on_delete=models.PROTECT, related_name='incidencias'
    )
    unidad = models.ForeignKey(
        Unidad, on_delete=models.SET_NULL, null=True, blank=True, related_name='incidencias'
    )
    tecnico = models.ForeignKey(
        Tecnico,
        verbose_name='Técnico asignado',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incidencias',
    )
    notas_internas = models.TextField('Notas internas (solo administrador)', blank=True)
    creada = models.DateTimeField('Creada', auto_now_add=True)
    actualizada = models.DateTimeField('Actualizada', auto_now=True)

    class Meta:
        ordering = ['-creada']
        verbose_name = 'incidencia'
        verbose_name_plural = 'incidencias'
        indexes = [
            models.Index(fields=['edificio', 'estado', '-creada'], name='inc_edif_estado_fecha'),
            models.Index(fields=['edificio', 'prioridad', 'estado'], name='inc_edif_prio_estado'),
            models.Index(fields=['tecnico', 'estado', '-creada'], name='inc_tecnico_estado_fecha'),
            models.Index(fields=['-creada'], name='inc_fecha_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(titulo=''), name='inc_titulo_no_vacio'),
            models.CheckConstraint(condition=models.Q(prioridad__in=['baja', 'media', 'alta']), name='inc_prioridad_valida'),
            models.CheckConstraint(condition=models.Q(estado__in=['pendiente', 'en_proceso', 'resuelta', 'cerrada']), name='inc_estado_valido'),
        ]

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


class EventoInmutableError(Exception):
    pass


class EventoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise EventoInmutableError('Los eventos son inmutables: no se pueden modificar.')

    def delete(self):
        raise EventoInmutableError('Los eventos son inmutables: no se pueden borrar.')


class EventoIncidencia(models.Model):
    """Historial de solo anexado: cada cambio importante deja una fila que nunca se edita."""

    CREADA = 'creada'
    ESTADO_CAMBIADO = 'estado_cambiado'
    TECNICO_ASIGNADO = 'tecnico_asignado'
    REABIERTA = 'reabierta'
    TIPOS = [
        (CREADA, 'Creada'),
        (ESTADO_CAMBIADO, 'Cambio de estado'),
        (TECNICO_ASIGNADO, 'Técnico asignado'),
        (REABIERTA, 'Reabierta'),
    ]

    incidencia = models.ForeignKey(Incidencia, on_delete=models.CASCADE, related_name='eventos')
    tipo = models.CharField(max_length=20, choices=TIPOS)
    estado_anterior = models.CharField(max_length=15, blank=True)
    estado_nuevo = models.CharField(max_length=15, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eventos_incidencia',
    )
    detalle = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    objects = EventoQuerySet.as_manager()

    class Meta:
        ordering = ['creado', 'id']

    def __str__(self):
        return f'{self.get_tipo_display()} - {self.incidencia_id}'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise EventoInmutableError('Los eventos son inmutables: no se pueden modificar.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise EventoInmutableError('Los eventos son inmutables: no se pueden borrar.')


class AuditoriaAcceso(models.Model):
    """Registro de accesos a recursos del sistema para trazabilidad M2."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    edificio = models.ForeignKey(Edificio, on_delete=models.SET_NULL, null=True, blank=True)
    ruta = models.CharField(max_length=500)
    metodo = models.CharField(max_length=10)
    resultado = models.PositiveSmallIntegerField(default=200)
    direccion_ip = models.GenericIPAddressField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        indexes = [models.Index(fields=['edificio', '-creado'], name='audit_edif_fecha_idx')]

    def __str__(self):
        return f'{self.usuario_id} {self.metodo} {self.ruta}'
