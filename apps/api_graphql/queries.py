"""Queries GraphQL de lecture — aucune mutation.

Pagination manuelle via page / perPage (camelCase côté client),
plafond MAX_PER_PAGE pour éviter les réponses démesurées.
"""

import graphene
from django.db.models import Count, Q
from graphql import GraphQLError

from apps.api_graphql.types import (
    CharacterType,
    FetchLogType,
    GenreType,
    MediaNode,
    StudioType,
)
from apps.catalog.models import Character, Genre, Media, Studio
from apps.collector.models import FetchLog

DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100
DEFAULT_FETCH_LOG_LIMIT = 10
MAX_FETCH_LOG_LIMIT = 50
PERM_VIEW_FETCHLOG = "collector.view_fetchlog"
MSG_AUTH_REQUISE = "Authentification requise"
MSG_PERMISSION_INSUFFISANTE = "Permission insuffisante"


def _est_authentifie(user):
    """True si user Django authentifié (propriété ou ancien callable)."""
    if user is None:
        return False
    flag = getattr(user, "is_authenticated", False)
    if callable(flag):
        flag = flag()
    return bool(flag)


def _utilisateur_contexte(info):
    context = info.context
    return getattr(context, "user", None)


def _exiger_authentification(info):
    """Refuse les requêtes anonymes. Retourne l'utilisateur authentifié."""
    user = _utilisateur_contexte(info)
    if not _est_authentifie(user):
        raise GraphQLError(MSG_AUTH_REQUISE)
    return user


def _exiger_acces_fetch_logs(info):
    """Réserve fetchLogs au staff authentifié ayant collector.view_fetchlog.

    Le superutilisateur conserve l'accès via has_perm Django, à condition
    d'être également staff (create_superuser le garantit).
    """
    user = _exiger_authentification(info)
    if not getattr(user, "is_staff", False) or not user.has_perm(PERM_VIEW_FETCHLOG):
        raise GraphQLError(MSG_PERMISSION_INSUFFISANTE)
    return user


def _borne_page(page, per_page):
    page = page if page is not None else DEFAULT_PAGE
    per_page = per_page if per_page is not None else DEFAULT_PER_PAGE
    try:
        page = int(page)
        per_page = int(per_page)
    except (TypeError, ValueError):
        page, per_page = DEFAULT_PAGE, DEFAULT_PER_PAGE
    page = max(1, page)
    per_page = min(MAX_PER_PAGE, max(1, per_page))
    return page, per_page


def _paginer(queryset, page, per_page):
    page, per_page = _borne_page(page, per_page)
    debut = (page - 1) * per_page
    return list(queryset[debut : debut + per_page])


class Query(graphene.ObjectType):
    all_media = graphene.List(
        MediaNode,
        media_type=graphene.String(),
        status=graphene.String(),
        season_year=graphene.Int(),
        genre=graphene.String(),
        search=graphene.String(),
        page=graphene.Int(default_value=DEFAULT_PAGE),
        per_page=graphene.Int(default_value=DEFAULT_PER_PAGE),
    )
    media = graphene.Field(MediaNode, id=graphene.ID(required=True))

    all_characters = graphene.List(
        CharacterType,
        search=graphene.String(),
        page=graphene.Int(default_value=DEFAULT_PAGE),
        per_page=graphene.Int(default_value=DEFAULT_PER_PAGE),
    )
    character = graphene.Field(CharacterType, id=graphene.ID(required=True))

    all_studios = graphene.List(
        StudioType,
        is_animation_studio=graphene.Boolean(),
    )
    studio = graphene.Field(StudioType, id=graphene.ID(required=True))

    all_genres = graphene.List(GenreType)

    fetch_logs = graphene.List(
        FetchLogType,
        limit=graphene.Int(default_value=DEFAULT_FETCH_LOG_LIMIT),
    )

    def resolve_all_media(
        self,
        info,
        media_type=None,
        status=None,
        season_year=None,
        genre=None,
        search=None,
        page=DEFAULT_PAGE,
        per_page=DEFAULT_PER_PAGE,
    ):
        qs = Media.objects.all().prefetch_related("genres").order_by("-popularity")
        if media_type:
            qs = qs.filter(media_type=media_type)
        if status:
            qs = qs.filter(status=status)
        if season_year is not None:
            qs = qs.filter(season_year=season_year)
        if genre:
            qs = qs.filter(genres__name__icontains=genre).distinct()
        if search:
            qs = qs.filter(
                Q(title_romaji__icontains=search)
                | Q(title_english__icontains=search)
                | Q(title_native__icontains=search)
            )
        return _paginer(qs, page, per_page)

    def resolve_media(self, info, id):
        try:
            return (
                Media.objects.prefetch_related(
                    "genres",
                    "studio_links__studio",
                    "character_links__character",
                ).get(pk=id)
            )
        except (Media.DoesNotExist, ValueError, TypeError):
            return None

    def resolve_all_characters(
        self, info, search=None, page=DEFAULT_PAGE, per_page=DEFAULT_PER_PAGE
    ):
        qs = Character.objects.all().order_by("name_full")
        if search:
            qs = qs.filter(
                Q(name_full__icontains=search) | Q(name_native__icontains=search)
            )
        return _paginer(qs, page, per_page)

    def resolve_character(self, info, id):
        try:
            return Character.objects.prefetch_related("media_links__media").get(pk=id)
        except (Character.DoesNotExist, ValueError, TypeError):
            return None

    def resolve_all_studios(self, info, is_animation_studio=None):
        qs = Studio.objects.all().order_by("name")
        if is_animation_studio is not None:
            qs = qs.filter(is_animation_studio=is_animation_studio)
        return qs

    def resolve_studio(self, info, id):
        try:
            return Studio.objects.prefetch_related("media_links__media").get(pk=id)
        except (Studio.DoesNotExist, ValueError, TypeError):
            return None

    def resolve_all_genres(self, info):
        return Genre.objects.annotate(
            _media_count=Count("media_items", distinct=True)
        ).order_by("name")

    def resolve_fetch_logs(self, info, limit=DEFAULT_FETCH_LOG_LIMIT):
        # TokenAuthentication DRF ne protège PAS automatiquement Graphene :
        # le contrôle staff + permission doit être explicite ici.
        _exiger_acces_fetch_logs(info)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = DEFAULT_FETCH_LOG_LIMIT
        limit = min(MAX_FETCH_LOG_LIMIT, max(1, limit))
        return list(FetchLog.objects.all().order_by("-started_at")[:limit])
