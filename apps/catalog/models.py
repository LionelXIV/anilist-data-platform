"""Modèles du catalogue : œuvres AniList, genres, studios et personnages.

Les valeurs enregistrées des énumérations sont les valeurs exactes retournées par
l'API GraphQL AniList. Seuls les libellés affichés sont traduits en français, afin
que le dédoublonnage et les filtres restent alignés sur la source de données.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class MediaType(models.TextChoices):
    """Type d'œuvre — champ `type` d'AniList."""

    ANIME = "ANIME", "Animé"
    MANGA = "MANGA", "Manga"


class MediaFormat(models.TextChoices):
    """Format de diffusion ou de publication — champ `format` d'AniList."""

    TV = "TV", "Série télévisée"
    TV_SHORT = "TV_SHORT", "Série télévisée courte"
    MOVIE = "MOVIE", "Film"
    SPECIAL = "SPECIAL", "Épisode spécial"
    OVA = "OVA", "OVA"
    ONA = "ONA", "ONA"
    MUSIC = "MUSIC", "Vidéoclip"
    MANGA = "MANGA", "Manga"
    NOVEL = "NOVEL", "Roman"
    ONE_SHOT = "ONE_SHOT", "One-shot"


class MediaStatus(models.TextChoices):
    """État d'avancement — champ `status` d'AniList."""

    FINISHED = "FINISHED", "Terminé"
    RELEASING = "RELEASING", "En cours"
    NOT_YET_RELEASED = "NOT_YET_RELEASED", "Pas encore paru"
    CANCELLED = "CANCELLED", "Annulé"
    HIATUS = "HIATUS", "En pause"


class MediaSeason(models.TextChoices):
    """Saison de diffusion — champ `season` d'AniList."""

    WINTER = "WINTER", "Hiver"
    SPRING = "SPRING", "Printemps"
    SUMMER = "SUMMER", "Été"
    FALL = "FALL", "Automne"


class CharacterRole(models.TextChoices):
    """Importance d'un personnage dans une œuvre — champ `role` d'AniList."""

    MAIN = "MAIN", "Principal"
    SUPPORTING = "SUPPORTING", "Secondaire"
    BACKGROUND = "BACKGROUND", "Arrière-plan"


class Genre(models.Model):
    """Genre d'une œuvre.

    AniList n'expose pas d'identifiant numérique pour les genres : ce sont des
    chaînes libres issues d'une liste fermée. Le nom sert donc de clé naturelle.
    """

    name = models.CharField(max_length=100, unique=True, verbose_name="Nom")

    class Meta:
        ordering = ["name"]
        verbose_name = "Genre"
        verbose_name_plural = "Genres"

    def __str__(self):
        return self.name or "Genre sans nom"


class Studio(models.Model):
    """Studio d'animation ou maison de production."""

    anilist_id = models.IntegerField(unique=True, verbose_name="Identifiant AniList")
    name = models.CharField(max_length=255, verbose_name="Nom")
    is_animation_studio = models.BooleanField(
        default=False,
        verbose_name="Studio d'animation",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Studio"
        verbose_name_plural = "Studios"

    def __str__(self):
        return self.name or f"Studio AniList #{self.anilist_id}"


class Media(models.Model):
    """Œuvre AniList : animé ou manga.

    AniList modélise les animés et les mangas par un type unique discriminé par
    `type`. Nous conservons ce choix pour éviter de dupliquer toute la couche API.
    Les champs propres à un type restent nuls pour l'autre : `episodes` pour les
    animés, `chapters` et `volumes` pour les mangas.
    """

    anilist_id = models.IntegerField(unique=True, verbose_name="Identifiant AniList")

    title_romaji = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Titre (romaji)"
    )
    title_english = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Titre (anglais)"
    )
    title_native = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Titre (natif)"
    )

    media_type = models.CharField(
        max_length=10,
        choices=MediaType.choices,
        db_index=True,
        verbose_name="Type",
    )
    format = models.CharField(
        max_length=20,
        choices=MediaFormat.choices,
        blank=True,
        null=True,
        verbose_name="Format",
    )
    status = models.CharField(
        max_length=20,
        choices=MediaStatus.choices,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Statut",
    )

    start_date = models.DateField(blank=True, null=True, verbose_name="Date de début")
    end_date = models.DateField(blank=True, null=True, verbose_name="Date de fin")

    season = models.CharField(
        max_length=10,
        choices=MediaSeason.choices,
        blank=True,
        null=True,
        verbose_name="Saison",
    )
    season_year = models.IntegerField(
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Année de la saison",
    )

    episodes = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        verbose_name="Nombre d'épisodes",
    )
    chapters = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        verbose_name="Nombre de chapitres",
    )
    volumes = models.IntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        verbose_name="Nombre de volumes",
    )

    average_score = models.FloatField(
        blank=True,
        null=True,
        db_index=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Score moyen",
    )
    popularity = models.IntegerField(
        blank=True,
        null=True,
        db_index=True,
        validators=[MinValueValidator(0)],
        verbose_name="Popularité",
    )

    cover_image_url = models.URLField(
        max_length=500, blank=True, null=True, verbose_name="Image de couverture"
    )
    banner_image_url = models.URLField(
        max_length=500, blank=True, null=True, verbose_name="Bannière"
    )
    synopsis = models.TextField(blank=True, null=True, verbose_name="Synopsis")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    genres = models.ManyToManyField(
        Genre,
        blank=True,
        related_name="media_items",
        verbose_name="Genres",
    )
    studios = models.ManyToManyField(
        Studio,
        through="MediaStudio",
        blank=True,
        related_name="media_items",
        verbose_name="Studios",
    )

    class Meta:
        ordering = ["-popularity"]
        verbose_name = "Œuvre"
        verbose_name_plural = "Œuvres"

    def __str__(self):
        return (
            self.title_romaji
            or self.title_english
            or self.title_native
            or f"Media AniList #{self.anilist_id}"
        )


class MediaStudio(models.Model):
    """Table de jointure entre une œuvre et un studio.

    Le drapeau `is_main` distingue le studio principal des studios producteurs
    secondaires, information qu'AniList expose par le champ `isMain` de la relation.
    """

    media = models.ForeignKey(
        Media,
        on_delete=models.CASCADE,
        related_name="studio_links",
        verbose_name="Œuvre",
    )
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="media_links",
        verbose_name="Studio",
    )
    is_main = models.BooleanField(default=False, verbose_name="Studio principal")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["media", "studio"],
                name="unique_media_studio",
            ),
        ]
        verbose_name = "Lien œuvre-studio"
        verbose_name_plural = "Liens œuvre-studio"

    def __str__(self):
        studio = str(self.studio) if self.studio_id else "studio inconnu"
        media = str(self.media) if self.media_id else "œuvre inconnue"
        role = "principal" if self.is_main else "secondaire"
        return f"{studio} — {media} ({role})"


class Character(models.Model):
    """Personnage d'une ou plusieurs œuvres."""

    anilist_id = models.IntegerField(unique=True, verbose_name="Identifiant AniList")
    name_full = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Nom complet"
    )
    name_native = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Nom natif"
    )
    image_url = models.URLField(
        max_length=500, blank=True, null=True, verbose_name="Image"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    gender = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="Genre"
    )
    # AniList retourne des valeurs non numériques ou des intervalles ("17-18",
    # "Unknown") : le champ reste une chaîne plutôt qu'un entier.
    age = models.CharField(max_length=50, blank=True, null=True, verbose_name="Âge")

    media = models.ManyToManyField(
        Media,
        through="CharacterMedia",
        blank=True,
        related_name="characters",
        verbose_name="Œuvres",
    )

    class Meta:
        ordering = ["name_full"]
        verbose_name = "Personnage"
        verbose_name_plural = "Personnages"

    def __str__(self):
        return (
            self.name_full
            or self.name_native
            or f"Personnage AniList #{self.anilist_id}"
        )


class CharacterMedia(models.Model):
    """Table de jointure entre un personnage et une œuvre, avec son rôle."""

    character = models.ForeignKey(
        Character,
        on_delete=models.CASCADE,
        related_name="media_links",
        verbose_name="Personnage",
    )
    media = models.ForeignKey(
        Media,
        on_delete=models.CASCADE,
        related_name="character_links",
        verbose_name="Œuvre",
    )
    role = models.CharField(
        max_length=20,
        choices=CharacterRole.choices,
        blank=True,
        null=True,
        verbose_name="Rôle",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character", "media"],
                name="unique_character_media",
            ),
        ]
        verbose_name = "Lien personnage-œuvre"
        verbose_name_plural = "Liens personnage-œuvre"

    def __str__(self):
        character = str(self.character) if self.character_id else "personnage inconnu"
        media = str(self.media) if self.media_id else "œuvre inconnue"
        role = self.get_role_display() if self.role else "rôle non précisé"
        return f"{character} — {media} ({role})"
