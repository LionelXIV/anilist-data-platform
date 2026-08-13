"""ViewSets catalogue en lecture seule."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.permissions import AllowAny

from apps.api_rest.filters import MediaFilter
from apps.api_rest.serializers import (
    CharacterSerializer,
    GenreSerializer,
    MediaDetailSerializer,
    MediaListSerializer,
    StudioSerializer,
)
from apps.catalog.models import Character, Genre, Media, Studio


class GenreViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Genre.objects.all().order_by("name")
    serializer_class = GenreSerializer
    permission_classes = [AllowAny]


class StudioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Studio.objects.all().order_by("name")
    serializer_class = StudioSerializer
    permission_classes = [AllowAny]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ("is_animation_studio",)
    search_fields = ("name",)


class CharacterViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Character.objects.all().order_by("name_full")
    serializer_class = CharacterSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ("name_full", "name_native")


class MediaViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    filterset_class = MediaFilter
    search_fields = ("title_romaji", "title_english", "title_native")
    ordering_fields = (
        "popularity",
        "average_score",
        "season_year",
        "title_romaji",
    )
    ordering = ("-popularity",)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return MediaDetailSerializer
        return MediaListSerializer

    def get_queryset(self):
        qs = Media.objects.all()
        if self.action == "retrieve":
            return qs.prefetch_related(
                "genres",
                "studio_links__studio",
                "character_links__character",
            )
        return qs.prefetch_related("genres")
