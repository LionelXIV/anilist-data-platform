"""Administration Django du catalogue AniList."""

from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from apps.catalog.models import (
    Character,
    CharacterMedia,
    Genre,
    Media,
    MediaStudio,
    Studio,
)


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ("name", "media_count")
    search_fields = ("name",)
    ordering = ("name",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_media_count=Count("media_items", distinct=True))
        )

    @admin.display(description="Œuvres", ordering="_media_count")
    def media_count(self, obj):
        return obj._media_count


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ("name", "anilist_id", "is_animation_studio", "media_count")
    list_filter = ("is_animation_studio",)
    search_fields = ("name", "anilist_id")
    ordering = ("name",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_media_count=Count("media_items", distinct=True))
        )

    @admin.display(description="Œuvres", ordering="_media_count")
    def media_count(self, obj):
        return obj._media_count


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ("name_full", "anilist_id", "gender", "age")
    list_filter = ("gender",)
    search_fields = ("name_full", "name_native", "anilist_id")
    ordering = ("name_full",)


class MediaStudioInline(admin.TabularInline):
    model = MediaStudio
    extra = 0
    autocomplete_fields = ("studio",)


class CharacterMediaInline(admin.TabularInline):
    model = CharacterMedia
    extra = 0
    autocomplete_fields = ("character",)


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = (
        "title_display",
        "anilist_id",
        "media_type_badge",
        "format",
        "status",
        "season_year",
        "average_score",
        "popularity",
    )
    list_filter = ("media_type", "format", "status", "season_year")
    search_fields = ("title_romaji", "title_english", "title_native", "anilist_id")
    ordering = ("-popularity",)
    list_per_page = 25
    date_hierarchy = "start_date"
    filter_horizontal = ("genres",)
    readonly_fields = ("anilist_id", "created_at", "updated_at")
    inlines = (MediaStudioInline, CharacterMediaInline)

    @admin.display(description="Titre", ordering="title_romaji")
    def title_display(self, obj):
        return (
            obj.title_romaji
            or obj.title_english
            or obj.title_native
            or f"Media AniList #{obj.anilist_id}"
        )

    @admin.display(description="Type", ordering="media_type")
    def media_type_badge(self, obj):
        if obj.media_type == "ANIME":
            return format_html(
                '<span class="badge bg-primary">'
                '<i class="fa-solid fa-tv" aria-hidden="true"></i> Animé</span>'
            )
        if obj.media_type == "MANGA":
            return format_html(
                '<span class="badge bg-secondary">'
                '<i class="fa-solid fa-book" aria-hidden="true"></i> Manga</span>'
            )
        return obj.media_type or "—"


@admin.register(MediaStudio)
class MediaStudioAdmin(admin.ModelAdmin):
    list_display = ("media", "studio", "is_main")
    list_filter = ("is_main",)
    search_fields = ("media__title_romaji", "studio__name")
    autocomplete_fields = ("media", "studio")


@admin.register(CharacterMedia)
class CharacterMediaAdmin(admin.ModelAdmin):
    list_display = ("character", "media", "role")
    list_filter = ("role",)
    search_fields = ("character__name_full", "media__title_romaji")
    autocomplete_fields = ("character", "media")
