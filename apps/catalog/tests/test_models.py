"""Tests unitaires des modèles du catalogue.

Deux niveaux de validation sont distingués, car ils ne se déclenchent pas au même
moment :

- les validateurs et les `choices` ne sont pas appliqués par un simple `save()` :
  ils exigent un appel explicite à `full_clean()` et lèvent une `ValidationError` ;
- les contraintes d'unicité sont appliquées par la base de données et lèvent une
  `IntegrityError`, encapsulée dans `transaction.atomic()` pour ne pas laisser la
  transaction du test dans un état cassé.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.catalog.models import (
    Character,
    CharacterMedia,
    CharacterRole,
    Genre,
    Media,
    MediaFormat,
    MediaSeason,
    MediaStatus,
    MediaStudio,
    MediaType,
    Studio,
)


class GenreModelTests(TestCase):
    def test_creation_minimale(self):
        genre = Genre.objects.create(name="Action")

        self.assertEqual(Genre.objects.count(), 1)
        self.assertEqual(genre.name, "Action")

    def test_str_retourne_le_nom(self):
        self.assertEqual(str(Genre(name="Aventure")), "Aventure")

    def test_str_repli_sans_nom(self):
        self.assertEqual(str(Genre(name="")), "Genre sans nom")

    def test_nom_unique(self):
        Genre.objects.create(name="Comédie")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Genre.objects.create(name="Comédie")

    def test_ordre_alphabetique(self):
        Genre.objects.create(name="Thriller")
        Genre.objects.create(name="Action")

        self.assertEqual(
            [genre.name for genre in Genre.objects.all()],
            ["Action", "Thriller"],
        )


class StudioModelTests(TestCase):
    def test_creation_minimale(self):
        studio = Studio.objects.create(anilist_id=43, name="ufotable")

        self.assertEqual(studio.anilist_id, 43)
        self.assertFalse(studio.is_animation_studio)

    def test_str_retourne_le_nom(self):
        self.assertEqual(str(Studio(anilist_id=43, name="ufotable")), "ufotable")

    def test_str_repli_sans_nom(self):
        self.assertEqual(str(Studio(anilist_id=99, name="")), "Studio AniList #99")

    def test_anilist_id_unique(self):
        Studio.objects.create(anilist_id=43, name="ufotable")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Studio.objects.create(anilist_id=43, name="Doublon")


class MediaModelTests(TestCase):
    @staticmethod
    def creer_anime(**champs):
        valeurs = {"anilist_id": 1, "media_type": MediaType.ANIME}
        valeurs.update(champs)
        return Media.objects.create(**valeurs)

    def test_creation_minimale(self):
        media = self.creer_anime(title_romaji="Cowboy Bebop")

        self.assertEqual(Media.objects.count(), 1)
        self.assertEqual(media.media_type, MediaType.ANIME)

    def test_str_priorite_romaji(self):
        media = Media(
            anilist_id=1,
            title_romaji="Hagane no Renkinjutsushi",
            title_english="Fullmetal Alchemist",
            title_native="鋼の錬金術師",
        )

        self.assertEqual(str(media), "Hagane no Renkinjutsushi")

    def test_str_repli_sur_anglais(self):
        media = Media(anilist_id=1, title_english="Attack on Titan")

        self.assertEqual(str(media), "Attack on Titan")

    def test_str_repli_sur_natif(self):
        media = Media(anilist_id=1, title_native="鋼の錬金術師")

        self.assertEqual(str(media), "鋼の錬金術師")

    def test_str_repli_sans_aucun_titre(self):
        self.assertEqual(str(Media(anilist_id=1234)), "Media AniList #1234")

    def test_anilist_id_unique(self):
        self.creer_anime()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Media.objects.create(anilist_id=1, media_type=MediaType.MANGA)

    def test_creation_manga_avec_chapitres_et_volumes(self):
        manga = Media.objects.create(
            anilist_id=30002,
            media_type=MediaType.MANGA,
            format=MediaFormat.MANGA,
            title_romaji="Berserk",
            chapters=374,
            volumes=42,
        )
        manga.full_clean()

        self.assertEqual(manga.chapters, 374)
        self.assertEqual(manga.volumes, 42)
        self.assertIsNone(manga.episodes)

    def test_creation_anime_avec_episodes(self):
        anime = Media.objects.create(
            anilist_id=1,
            media_type=MediaType.ANIME,
            format=MediaFormat.TV,
            title_romaji="Cowboy Bebop",
            episodes=26,
            season=MediaSeason.SPRING,
            season_year=1998,
        )
        anime.full_clean()

        self.assertEqual(anime.episodes, 26)
        self.assertIsNone(anime.chapters)
        self.assertIsNone(anime.volumes)

    def test_champs_nullables_reellement_acceptes(self):
        media = self.creer_anime()
        media.full_clean()
        media.refresh_from_db()

        for champ in (
            "title_romaji",
            "title_english",
            "title_native",
            "format",
            "status",
            "start_date",
            "end_date",
            "season",
            "season_year",
            "episodes",
            "chapters",
            "volumes",
            "average_score",
            "popularity",
            "cover_image_url",
            "banner_image_url",
            "synopsis",
        ):
            with self.subTest(champ=champ):
                self.assertIsNone(getattr(media, champ))

    def test_score_negatif_rejete(self):
        media = Media(anilist_id=1, media_type=MediaType.ANIME, average_score=-1)

        with self.assertRaises(ValidationError) as contexte:
            media.full_clean()

        self.assertIn("average_score", contexte.exception.message_dict)

    def test_score_superieur_a_cent_rejete(self):
        media = Media(anilist_id=1, media_type=MediaType.ANIME, average_score=100.5)

        with self.assertRaises(ValidationError) as contexte:
            media.full_clean()

        self.assertIn("average_score", contexte.exception.message_dict)

    def test_score_aux_bornes_accepte(self):
        for score in (0, 100):
            with self.subTest(score=score):
                media = Media(
                    anilist_id=1000 + score,
                    media_type=MediaType.ANIME,
                    average_score=score,
                )
                media.full_clean()

    def test_popularite_negative_rejetee(self):
        media = Media(anilist_id=1, media_type=MediaType.ANIME, popularity=-5)

        with self.assertRaises(ValidationError) as contexte:
            media.full_clean()

        self.assertIn("popularity", contexte.exception.message_dict)

    def test_compteurs_negatifs_rejetes(self):
        for champ in ("episodes", "chapters", "volumes"):
            with self.subTest(champ=champ):
                media = Media(
                    anilist_id=1,
                    media_type=MediaType.ANIME,
                    **{champ: -1},
                )

                with self.assertRaises(ValidationError) as contexte:
                    media.full_clean()

                self.assertIn(champ, contexte.exception.message_dict)

    def test_type_invalide_rejete(self):
        media = Media(anilist_id=1, media_type="LIVRE_AUDIO")

        with self.assertRaises(ValidationError) as contexte:
            media.full_clean()

        self.assertIn("media_type", contexte.exception.message_dict)

    def test_format_invalide_rejete(self):
        media = Media(anilist_id=1, media_type=MediaType.ANIME, format="FEUILLETON")

        with self.assertRaises(ValidationError) as contexte:
            media.full_clean()

        self.assertIn("format", contexte.exception.message_dict)

    def test_statut_invalide_rejete(self):
        media = Media(anilist_id=1, media_type=MediaType.ANIME, status="EN_ATTENTE")

        with self.assertRaises(ValidationError) as contexte:
            media.full_clean()

        self.assertIn("status", contexte.exception.message_dict)

    def test_saison_invalide_rejetee(self):
        media = Media(anilist_id=1, media_type=MediaType.ANIME, season="MOUSSON")

        with self.assertRaises(ValidationError) as contexte:
            media.full_clean()

        self.assertIn("season", contexte.exception.message_dict)

    def test_valeurs_denumerations_conformes_a_anilist(self):
        self.assertEqual(MediaType.ANIME.value, "ANIME")
        self.assertEqual(MediaFormat.ONE_SHOT.value, "ONE_SHOT")
        self.assertEqual(MediaStatus.NOT_YET_RELEASED.value, "NOT_YET_RELEASED")
        self.assertEqual(MediaSeason.FALL.value, "FALL")
        self.assertEqual(CharacterRole.SUPPORTING.value, "SUPPORTING")

    def test_relation_genres(self):
        media = self.creer_anime(title_romaji="Cowboy Bebop")
        action = Genre.objects.create(name="Action")
        drame = Genre.objects.create(name="Drame")
        media.genres.add(action, drame)

        self.assertEqual(media.genres.count(), 2)
        self.assertEqual(action.media_items.count(), 1)
        self.assertEqual(action.media_items.first(), media)

    def test_titre_natif_conserve_les_caracteres_japonais(self):
        media = self.creer_anime(title_native="鋼の錬金術師")
        media.refresh_from_db()

        self.assertEqual(media.title_native, "鋼の錬金術師")


class MediaStudioModelTests(TestCase):
    def setUp(self):
        self.media = Media.objects.create(
            anilist_id=1, media_type=MediaType.ANIME, title_romaji="Cowboy Bebop"
        )
        self.studio = Studio.objects.create(
            anilist_id=14, name="Sunrise", is_animation_studio=True
        )

    def test_creation_relation_valide(self):
        lien = MediaStudio.objects.create(
            media=self.media, studio=self.studio, is_main=True
        )
        lien.full_clean()

        self.assertTrue(lien.is_main)
        self.assertEqual(MediaStudio.objects.count(), 1)

    def test_is_main_par_defaut_faux(self):
        lien = MediaStudio.objects.create(media=self.media, studio=self.studio)

        self.assertFalse(lien.is_main)

    def test_relations_inverses(self):
        MediaStudio.objects.create(media=self.media, studio=self.studio)

        self.assertEqual(self.media.studio_links.count(), 1)
        self.assertEqual(self.studio.media_links.count(), 1)
        self.assertEqual(self.media.studios.first(), self.studio)
        self.assertEqual(self.studio.media_items.first(), self.media)

    def test_paire_dupliquee_refusee(self):
        MediaStudio.objects.create(media=self.media, studio=self.studio)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MediaStudio.objects.create(media=self.media, studio=self.studio)

    def test_str_lisible(self):
        lien = MediaStudio.objects.create(
            media=self.media, studio=self.studio, is_main=True
        )

        self.assertIsInstance(str(lien), str)
        self.assertIn("Sunrise", str(lien))
        self.assertIn("principal", str(lien))


class CharacterModelTests(TestCase):
    def test_creation_minimale(self):
        personnage = Character.objects.create(
            anilist_id=1, name_full="Spike Spiegel"
        )

        self.assertEqual(Character.objects.count(), 1)
        self.assertEqual(personnage.name_full, "Spike Spiegel")

    def test_str_priorite_nom_complet(self):
        personnage = Character(
            anilist_id=1, name_full="Spike Spiegel", name_native="スパイク"
        )

        self.assertEqual(str(personnage), "Spike Spiegel")

    def test_str_repli_sur_nom_natif(self):
        self.assertEqual(str(Character(anilist_id=1, name_native="スパイク")), "スパイク")

    def test_str_repli_sans_aucun_nom(self):
        self.assertEqual(str(Character(anilist_id=77)), "Personnage AniList #77")

    def test_anilist_id_unique(self):
        Character.objects.create(anilist_id=1, name_full="Spike Spiegel")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Character.objects.create(anilist_id=1, name_full="Doublon")

    def test_age_accepte_une_valeur_non_numerique(self):
        personnage = Character.objects.create(
            anilist_id=2, name_full="Edward", age="13-14"
        )
        personnage.full_clean()

        self.assertEqual(personnage.age, "13-14")


class CharacterMediaModelTests(TestCase):
    def setUp(self):
        self.media = Media.objects.create(
            anilist_id=1, media_type=MediaType.ANIME, title_romaji="Cowboy Bebop"
        )
        self.character = Character.objects.create(
            anilist_id=1, name_full="Spike Spiegel"
        )

    def test_creation_relation_valide(self):
        lien = CharacterMedia.objects.create(
            character=self.character, media=self.media, role=CharacterRole.MAIN
        )
        lien.full_clean()

        self.assertEqual(lien.role, CharacterRole.MAIN)

    def test_relations_inverses(self):
        CharacterMedia.objects.create(
            character=self.character, media=self.media, role=CharacterRole.MAIN
        )

        self.assertEqual(self.character.media_links.count(), 1)
        self.assertEqual(self.media.character_links.count(), 1)
        self.assertEqual(self.character.media.first(), self.media)
        self.assertEqual(self.media.characters.first(), self.character)

    def test_paire_dupliquee_refusee(self):
        CharacterMedia.objects.create(character=self.character, media=self.media)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CharacterMedia.objects.create(
                    character=self.character, media=self.media
                )

    def test_role_invalide_rejete(self):
        lien = CharacterMedia(
            character=self.character, media=self.media, role="FIGURANT"
        )

        with self.assertRaises(ValidationError) as contexte:
            lien.full_clean()

        self.assertIn("role", contexte.exception.message_dict)

    def test_role_nullable(self):
        lien = CharacterMedia.objects.create(
            character=self.character, media=self.media
        )
        lien.full_clean()

        self.assertIsNone(lien.role)

    def test_str_lisible(self):
        lien = CharacterMedia.objects.create(
            character=self.character, media=self.media, role=CharacterRole.MAIN
        )

        self.assertIsInstance(str(lien), str)
        self.assertIn("Spike Spiegel", str(lien))
