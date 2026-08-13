"""Tests de l'API REST catalogue (lecture seule)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import (
    Character,
    CharacterMedia,
    Genre,
    Media,
    MediaStudio,
    Studio,
)


class CatalogueAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.genre_action = Genre.objects.create(name="Action")
        cls.genre_drama = Genre.objects.create(name="Drama")
        cls.studio_main = Studio.objects.create(
            anilist_id=100, name="MAPPA", is_animation_studio=True
        )
        cls.studio_sec = Studio.objects.create(
            anilist_id=101, name="Aniplex", is_animation_studio=False
        )
        cls.media = Media.objects.create(
            anilist_id=145064,
            title_romaji="Jujutsu Kaisen 2nd Season",
            title_english="Jujutsu Kaisen Season 2",
            title_native="呪術廻戦 第2期",
            media_type="ANIME",
            format="TV",
            status="FINISHED",
            season_year=2023,
            average_score=86,
            popularity=300000,
            cover_image_url="https://example.test/cover.jpg",
        )
        cls.media_manga = Media.objects.create(
            anilist_id=300,
            title_romaji="One Piece",
            media_type="MANGA",
            format="MANGA",
            status="RELEASING",
            season_year=1997,
            average_score=90,
            popularity=500000,
        )
        cls.media.genres.add(cls.genre_action, cls.genre_drama)
        MediaStudio.objects.create(
            media=cls.media, studio=cls.studio_main, is_main=True
        )
        MediaStudio.objects.create(
            media=cls.media, studio=cls.studio_sec, is_main=False
        )
        cls.character = Character.objects.create(
            anilist_id=127212,
            name_full="Yuji Itadori",
            name_native="虎杖悠仁",
            image_url="https://example.test/yuji.jpg",
        )
        CharacterMedia.objects.create(
            character=cls.character, media=cls.media, role="MAIN"
        )

    def test_list_et_retrieve_quatre_ressources(self):
        for basename in ("genre", "studio", "character", "media"):
            with self.subTest(basename=basename):
                liste = self.client.get(reverse(f"{basename}-list"))
                self.assertEqual(liste.status_code, status.HTTP_200_OK)
                self.assertIn("results", liste.data)

        detail = self.client.get(
            reverse("media-detail", args=[self.media.pk])
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)

    def test_media_detail_expose_is_main_et_role_reels(self):
        reponse = self.client.get(reverse("media-detail", args=[self.media.pk]))
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)

        self.assertEqual(
            sorted(reponse.data["genres"]), ["Action", "Drama"]
        )

        studios = {s["name"]: s for s in reponse.data["studios"]}
        self.assertTrue(studios["MAPPA"]["is_main"])
        self.assertFalse(studios["Aniplex"]["is_main"])
        self.assertTrue(studios["MAPPA"]["is_animation_studio"])

        personnages = reponse.data["characters"]
        self.assertEqual(len(personnages), 1)
        self.assertEqual(personnages[0]["name_full"], "Yuji Itadori")
        self.assertEqual(personnages[0]["role"], "MAIN")
        self.assertEqual(personnages[0]["name_native"], "虎杖悠仁")

    def test_pagination_active(self):
        reponse = self.client.get(reverse("media-list"))
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        for cle in ("count", "next", "previous", "results"):
            self.assertIn(cle, reponse.data)

    def test_filtre_media_type(self):
        reponse = self.client.get(
            reverse("media-list"), {"media_type": "ANIME"}
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        types = {item["media_type"] for item in reponse.data["results"]}
        self.assertEqual(types, {"ANIME"})

    def test_filtre_season_year_min(self):
        reponse = self.client.get(
            reverse("media-list"), {"season_year_min": 2020}
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        ids = {item["anilist_id"] for item in reponse.data["results"]}
        self.assertIn(145064, ids)
        self.assertNotIn(300, ids)

    def test_filtre_average_score_min(self):
        reponse = self.client.get(
            reverse("media-list"), {"average_score_min": 88}
        )
        ids = {item["anilist_id"] for item in reponse.data["results"]}
        self.assertIn(300, ids)
        self.assertNotIn(145064, ids)

    def test_recherche_textuelle_media(self):
        reponse = self.client.get(
            reverse("media-list"), {"search": "Jujutsu"}
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        titres = [item["title_romaji"] for item in reponse.data["results"]]
        self.assertIn("Jujutsu Kaisen 2nd Season", titres)
        self.assertNotIn("One Piece", titres)

    def test_tri_par_popularite(self):
        reponse = self.client.get(
            reverse("media-list"), {"ordering": "popularity"}
        )
        popularites = [item["popularity"] for item in reponse.data["results"]]
        self.assertEqual(popularites, sorted(popularites))

    def test_ecriture_refusee_sur_catalogue(self):
        url = reverse("media-list")
        for methode, kwargs in (
            ("post", {"data": {"anilist_id": 1, "media_type": "ANIME"}}),
            ("put", {"data": {"anilist_id": 1, "media_type": "ANIME"}}),
            ("patch", {"data": {"title_romaji": "X"}}),
            ("delete", {}),
        ):
            with self.subTest(methode=methode):
                if methode in ("put", "patch", "delete"):
                    cible = reverse("media-detail", args=[self.media.pk])
                else:
                    cible = url
                reponse = getattr(self.client, methode)(cible, **kwargs)
                self.assertIn(
                    reponse.status_code,
                    (
                        status.HTTP_405_METHOD_NOT_ALLOWED,
                        status.HTTP_403_FORBIDDEN,
                    ),
                )

    def test_list_genres_et_studios(self):
        self.assertEqual(
            self.client.get(reverse("genre-list")).status_code,
            status.HTTP_200_OK,
        )
        reponse = self.client.get(
            reverse("studio-list"), {"is_animation_studio": "true"}
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        for item in reponse.data["results"]:
            self.assertTrue(item["is_animation_studio"])
