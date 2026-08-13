"""Serializers de l'API REST catalogue.

Noms de relations du modèle catalogue :
- Media.genres (M2M Genre, related_name media_items)
- Media.studio_links (FK inverse MediaStudio) pour is_main
- Media.character_links (FK inverse CharacterMedia) pour role
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.catalog.models import Character, Genre, Media, Studio

User = get_user_model()


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("id", "name")


class StudioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Studio
        fields = ("id", "anilist_id", "name", "is_animation_studio")


class CharacterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Character
        fields = (
            "id",
            "anilist_id",
            "name_full",
            "name_native",
            "image_url",
            "gender",
            "age",
        )


class MediaListSerializer(serializers.ModelSerializer):
    genres = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = (
            "id",
            "anilist_id",
            "title_romaji",
            "title_english",
            "media_type",
            "format",
            "status",
            "season_year",
            "average_score",
            "popularity",
            "cover_image_url",
            "genres",
        )

    def get_genres(self, obj):
        return [genre.name for genre in obj.genres.all()]


class MediaDetailSerializer(MediaListSerializer):
    studios = serializers.SerializerMethodField()
    characters = serializers.SerializerMethodField()

    class Meta(MediaListSerializer.Meta):
        fields = MediaListSerializer.Meta.fields + (
            "title_native",
            "banner_image_url",
            "synopsis",
            "start_date",
            "end_date",
            "season",
            "episodes",
            "chapters",
            "volumes",
            "studios",
            "characters",
        )

    def get_studios(self, obj):
        # is_main provient de MediaStudio (related_name studio_links).
        return [
            {
                "id": lien.studio_id,
                "name": lien.studio.name,
                "is_animation_studio": lien.studio.is_animation_studio,
                "is_main": lien.is_main,
            }
            for lien in obj.studio_links.all()
        ]

    def get_characters(self, obj):
        # role provient de CharacterMedia (related_name character_links).
        return [
            {
                "id": lien.character_id,
                "name_full": lien.character.name_full,
                "name_native": lien.character.name_native,
                "image_url": lien.character.image_url,
                "role": lien.role,
            }
            for lien in obj.character_links.all()
        ]


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "Ce nom d'utilisateur est déjà pris."
            )
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email") or "",
            password=validated_data["password"],
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "date_joined",
        )
        read_only_fields = ("id", "username", "date_joined")


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Mise à jour partielle : email, first_name, last_name uniquement."""

    email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")
