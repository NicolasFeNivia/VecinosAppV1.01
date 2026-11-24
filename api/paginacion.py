from rest_framework.pagination import CursorPagination


class PaginacionCursor(CursorPagination):
    """Paginación por cursor: estable aunque lleguen incidencias nuevas mientras se pagina."""

    page_size = 20
    page_size_query_param = 'limite'
    max_page_size = 100
    ordering = ('-creada', '-id')
