"""Filtres django-filter pour l'API catalogue.

Convention retenue pour les plages numériques : paramètres explicites
`season_year_min` / `season_year_max` (lookup `gte` / `lte`), plutôt que
les suffixes Django bruts `season_year__gte` dans l'URL. Même schéma pour
`average_score_min` / `average_score_max` et `popularity_min`.

Le filtre `genres` porte sur `genres__name` en `icontains` (insensible à
la casse, utile pour une recherche partielle du nom de genre).
"""

import django_filters

from apps.catalog.models import Media


class MediaFilter(django_filters.FilterSet):
    media_type = django_filters.CharFilter(field_name="media_type", lookup_expr="exact")
    format = django_filters.CharFilter(field_name="format", lookup_expr="exact")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")

    season_year = django_filters.NumberFilter(
        field_name="season_year", lookup_expr="exact"
    )
    season_year_min = django_filters.NumberFilter(
        field_name="season_year", lookup_expr="gte"
    )
    season_year_max = django_filters.NumberFilter(
        field_name="season_year", lookup_expr="lte"
    )

    average_score_min = django_filters.NumberFilter(
        field_name="average_score", lookup_expr="gte"
    )
    average_score_max = django_filters.NumberFilter(
        field_name="average_score", lookup_expr="lte"
    )

    popularity_min = django_filters.NumberFilter(
        field_name="popularity", lookup_expr="gte"
    )

    genres = django_filters.CharFilter(
        field_name="genres__name", lookup_expr="icontains"
    )

    class Meta:
        model = Media
        fields = (
            "media_type",
            "format",
            "status",
            "season_year",
            "season_year_min",
            "season_year_max",
            "average_score_min",
            "average_score_max",
            "popularity_min",
            "genres",
        )
