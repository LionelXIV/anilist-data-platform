"""Agrégations du tableau de bord statistiques.

Une seule fonction alimente la page HTML et GET /api/stats/, afin que
les chiffres présentés ne divergent jamais entre les deux surfaces.
"""

from django.db.models import Count, Q
from django.utils import timezone

from apps.catalog.models import Character, Genre, Media, Studio


def _titre_media(media):
    return (
        media.title_romaji
        or media.title_english
        or media.title_native
        or f"Media AniList #{media.anilist_id}"
    )


def get_dashboard_data():
    """Calcule toutes les statistiques du tableau de bord."""

    total_anime = Media.objects.filter(media_type="ANIME").count()
    total_manga = Media.objects.filter(media_type="MANGA").count()
    total_characters = Character.objects.count()
    total_studios = Studio.objects.count()
    total_genres = Genre.objects.count()

    genre_distribution = list(
        Genre.objects.annotate(count=Count("media_items", distinct=True))
        .filter(count__gt=0)
        .order_by("-count", "name")
        .values("name", "count")
    )

    works_by_year = list(
        Media.objects.exclude(season_year__isnull=True)
        .values("season_year")
        .annotate(count=Count("id"))
        .order_by("season_year")
    )
    works_by_year = [
        {"year": ligne["season_year"], "count": ligne["count"]}
        for ligne in works_by_year
    ]

    top_popular = [
        {
            "id": media.id,
            "title": _titre_media(media),
            "popularity": media.popularity,
            "cover_image_url": media.cover_image_url,
            "media_type": media.media_type,
        }
        for media in Media.objects.exclude(popularity__isnull=True).order_by(
            "-popularity"
        )[:10]
    ]

    top_rated = [
        {
            "id": media.id,
            "title": _titre_media(media),
            "average_score": media.average_score,
            "cover_image_url": media.cover_image_url,
            "media_type": media.media_type,
        }
        for media in Media.objects.exclude(average_score__isnull=True).order_by(
            "-average_score"
        )[:10]
    ]

    # Studios principaux d'animes uniquement (is_main + media_type=ANIME).
    filtre_principal_anime = Q(
        media_links__is_main=True,
        media_links__media__media_type="ANIME",
    )
    anime_by_studio = list(
        Studio.objects.filter(filtre_principal_anime)
        .annotate(
            anime_count=Count(
                "media_links",
                filter=filtre_principal_anime,
                distinct=True,
            )
        )
        .filter(anime_count__gt=0)
        .order_by("-anime_count", "name")
        .values("name", "anime_count")[:10]
    )

    return {
        "total_anime": total_anime,
        "total_manga": total_manga,
        "total_characters": total_characters,
        "total_studios": total_studios,
        "total_genres": total_genres,
        "genre_distribution": genre_distribution,
        "works_by_year": works_by_year,
        "top_popular": top_popular,
        "top_rated": top_rated,
        "anime_by_studio": anime_by_studio,
        "generated_at": timezone.now().isoformat(),
    }
