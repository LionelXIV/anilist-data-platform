"""Types Graphene pour le catalogue AniList (lecture seule).

Related_name du modèle catalogue :
studio_links, character_links, media_links, media_items, characters.

Le type GraphQL de Media s'appelle MediaNode pour éviter toute collision
avec apps.catalog.models.MediaType (TextChoices ANIME/MANGA).

Pour is_main et role, des ObjectType dédiés exposent la paire
(entité + attribut de jonction) plutôt que le DjangoObjectType brut
des tables through — plus simple et aligné sur le JSON REST.
"""

import graphene
from graphene_django import DjangoObjectType

from apps.catalog.models import Character, Genre, Media, Studio
from apps.collector.models import FetchLog


class GenreType(DjangoObjectType):
    media_count = graphene.Int()

    class Meta:
        model = Genre
        fields = ("id", "name")

    def resolve_media_count(self, info):
        if hasattr(self, "_media_count"):
            return self._media_count
        return self.media_items.count()


class StudioType(DjangoObjectType):
    media_links = graphene.List(lambda: StudioMediaLinkType)

    class Meta:
        model = Studio
        fields = ("id", "anilist_id", "name", "is_animation_studio")

    def resolve_media_links(self, info):
        return [
            StudioMediaLinkType(
                id=lien.media_id,
                title_romaji=lien.media.title_romaji,
                title_english=lien.media.title_english,
                average_score=lien.media.average_score,
                popularity=lien.media.popularity,
                is_main=lien.is_main,
            )
            for lien in self.media_links.select_related("media").all()
        ]


class CharacterType(DjangoObjectType):
    appearances = graphene.List(lambda: CharacterMediaLinkType)

    class Meta:
        model = Character
        fields = (
            "id",
            "anilist_id",
            "name_full",
            "name_native",
            "image_url",
            "description",
            "gender",
            "age",
        )

    def resolve_appearances(self, info):
        return [
            CharacterMediaLinkType(
                id=lien.media_id,
                title_romaji=lien.media.title_romaji,
                title_english=lien.media.title_english,
                media_type=lien.media.media_type,
                role=lien.role,
            )
            for lien in self.media_links.select_related("media").all()
        ]


class MediaStudioLinkType(graphene.ObjectType):
    """Studio lié à une œuvre, avec is_main issu de MediaStudio."""

    id = graphene.Int()
    name = graphene.String()
    is_animation_studio = graphene.Boolean()
    is_main = graphene.Boolean()


class CharacterRoleLinkType(graphene.ObjectType):
    """Personnage lié à une œuvre, avec role issu de CharacterMedia."""

    id = graphene.Int()
    name_full = graphene.String()
    name_native = graphene.String()
    image_url = graphene.String()
    role = graphene.String()


class StudioMediaLinkType(graphene.ObjectType):
    """Œuvre liée à un studio, avec is_main issu de MediaStudio."""

    id = graphene.Int()
    title_romaji = graphene.String()
    title_english = graphene.String()
    average_score = graphene.Float()
    popularity = graphene.Int()
    is_main = graphene.Boolean()


class CharacterMediaLinkType(graphene.ObjectType):
    """Apparition d'un personnage dans une œuvre, avec role."""

    id = graphene.Int()
    title_romaji = graphene.String()
    title_english = graphene.String()
    media_type = graphene.String()
    role = graphene.String()


class MediaNode(DjangoObjectType):
    """Œuvre AniList — champs alignés sur MediaDetailSerializer."""

    studios = graphene.List(MediaStudioLinkType)
    # Champ GraphQL « characters » (avec role) : ne pas confondre avec le M2M
    # Media.characters, volontairement absent de Meta.fields.
    characters = graphene.List(CharacterRoleLinkType)

    class Meta:
        model = Media
        fields = (
            "id",
            "anilist_id",
            "title_romaji",
            "title_english",
            "title_native",
            "media_type",
            "format",
            "status",
            "season_year",
            "average_score",
            "popularity",
            "cover_image_url",
            "banner_image_url",
            "synopsis",
            "start_date",
            "end_date",
            "season",
            "episodes",
            "chapters",
            "volumes",
            "genres",
        )

    def resolve_studios(self, info):
        return [
            MediaStudioLinkType(
                id=lien.studio_id,
                name=lien.studio.name,
                is_animation_studio=lien.studio.is_animation_studio,
                is_main=lien.is_main,
            )
            for lien in self.studio_links.select_related("studio").all()
        ]

    def resolve_characters(self, info):
        return [
            CharacterRoleLinkType(
                id=lien.character_id,
                name_full=lien.character.name_full,
                name_native=lien.character.name_native,
                image_url=lien.character.image_url,
                role=lien.role,
            )
            for lien in self.character_links.select_related("character").all()
        ]


class FetchLogType(DjangoObjectType):
    class Meta:
        model = FetchLog
        fields = (
            "id",
            "started_at",
            "finished_at",
            "status",
            "media_type",
            "criteria",
            "records_fetched",
            "records_created",
            "records_updated",
            "error_message",
        )
