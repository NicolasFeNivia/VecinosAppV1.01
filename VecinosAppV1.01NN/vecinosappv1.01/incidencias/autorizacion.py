"""Política central de permisos por rol y recurso (M2)."""
ACCIONES = ('listar', 'ver_detalle', 'crear', 'comentar', 'editar', 'asignar_tecnico', 'cambiar_estado', 'eliminar')
ROLES = ('Residente', 'Administrador', 'Técnico', 'Auditor')

MATRIZ_PERMISOS = {
    'Residente': {'listar', 'ver_detalle', 'crear', 'comentar', 'editar', 'eliminar'},
    'Administrador': set(ACCIONES),
    'Técnico': {'listar', 'ver_detalle', 'comentar'},
    'Auditor': {'listar', 'ver_detalle'},
}

def puede_realizar(usuario, accion, incidencia=None):
    """Comprueba rol y pertenencia al edificio; los permisos no sustituyen el filtro del QuerySet."""
    if not usuario or not usuario.is_authenticated or accion not in ACCIONES:
        return False
    if usuario.is_superuser:
        return True
    if incidencia is None:
        return usuario.groups.filter(name='Administrador').exists() and accion in MATRIZ_PERMISOS['Administrador']
    edificio = incidencia.edificio
    if usuario.groups.filter(name='Administrador').exists() and edificio.administradores.filter(pk=usuario.pk).exists():
        return accion in MATRIZ_PERMISOS['Administrador']
    if usuario.groups.filter(name='Auditor').exists() and edificio.auditores.filter(pk=usuario.pk).exists():
        return accion in MATRIZ_PERMISOS['Auditor']
    if usuario.groups.filter(name='Técnico').exists() and incidencia.tecnico_id and incidencia.tecnico.usuario_id == usuario.pk and incidencia.tecnico.edificios.filter(pk=edificio.pk).exists():
        return accion in MATRIZ_PERMISOS['Técnico']
    if usuario.groups.filter(name='Residente').exists() and incidencia.residente_id == usuario.pk:
        if accion == 'editar':
            return incidencia.estado == 'pendiente'
        if accion == 'eliminar':
            return incidencia.estado == 'pendiente'
        return accion in MATRIZ_PERMISOS['Residente']
    return False
