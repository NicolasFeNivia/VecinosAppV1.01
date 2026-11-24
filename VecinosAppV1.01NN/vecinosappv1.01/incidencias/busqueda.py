"""Búsqueda optimizada. PostgreSQL usa trigramas; SQLite conserva fallback funcional."""
from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection
from django.db.models import Q
from .models import Incidencia

def buscar_incidencias(queryset, termino):
    termino = (termino or '').strip()
    if not termino:
        return queryset
    if connection.vendor == 'postgresql' and len(termino) >= 3:
        return queryset.annotate(
            similitud_titulo=TrigramSimilarity('titulo', termino),
            similitud_descripcion=TrigramSimilarity('descripcion', termino),
        ).filter(Q(similitud_titulo__gt=0.12) | Q(similitud_descripcion__gt=0.08)).order_by(
            '-similitud_titulo', '-similitud_descripcion', '-creada'
        )
    return queryset.filter(Q(titulo__icontains=termino) | Q(descripcion__icontains=termino))
