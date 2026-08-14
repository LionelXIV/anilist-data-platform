"""Tests du tableau de bord statistiques."""

from django.db.models import Count, Q
from django.test import Client, TestCase
from django.urls import reverse

from apps.catalog.models import (
    Character,
    Genre,
    Media,
    MediaStudio,
    Studio,
)
from apps.stats.services import get_dashboard_data


class DashboardDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.g_action = Genre.objects.create(name="Action")
        cls.g_drama = Genre.objects.create(name="Drama")
        Genre.objects.create(name="Orphelin")  # sans œuvre → exclu du graphique

        cls.studio_main = Studio.objects.create(
            anilist_id=1, name="MAPPA", is_animation_studio=True
        )
        cls.studio_sec = Studio.objects.create(
            anilist_id=2, name="Aniplex", is_animation_studio=False
        )
        cls.studio_manga = Studio.objects.create(
            anilist_id=3, name="Shueisha", is_animation_studio=False
        )

        cls.anime_a = Media.objects.create(
            anilist_id=10,
            title_romaji="Anime A",
            media_type="ANIME",
            season_year=2023,
            popularity=100,
            average_score=90,
        )
        cls.anime_b = Media.objects.create(
            anilist_id=11,
            title_romaji="Anime B",
            media_type="ANIME",
            season_year=2023,
            popularity=200,
            average_score=80,
        )
        cls.manga = Media.objects.create(
            anilist_id=12,
            title_romaji="Manga X",
            media_type="MANGA",
            season_year=2020,
            popularity=50,
            average_score=95,
        )

        cls.anime_a.genres.add(cls.g_action, cls.g_drama)
        cls.anime_b.genres.add(cls.g_action)
        cls.manga.genres.add(cls.g_drama)

        MediaStudio.objects.create(
            media=cls.anime_a, studio=cls.studio_main, is_main=True
        )
        MediaStudio.objects.create(
            media=cls.anime_b, studio=cls.studio_main, is_main=True
        )
        # Studio secondaire d'un animé : ne doit pas compter dans anime_by_studio.
        MediaStudio.objects.create(
            media=cls.anime_a, studio=cls.studio_sec, is_main=False
        )
        # Studio principal d'un manga seulement : ne doit pas apparaître.
        MediaStudio.objects.create(
            media=cls.manga, studio=cls.studio_manga, is_main=True
        )

        Character.objects.create(anilist_id=100, name_full="Perso 1")
        Character.objects.create(anilist_id=101, name_full="Perso 2")

    def test_get_dashboard_data_coherent_avec_orm_independant(self):
        data = get_dashboard_data()

        self.assertEqual(
            data["total_anime"],
            Media.objects.filter(media_type="ANIME").count(),
        )
        self.assertEqual(
            data["total_manga"],
            Media.objects.filter(media_type="MANGA").count(),
        )
        self.assertEqual(data["total_characters"], Character.objects.count())
        self.assertEqual(data["total_studios"], Studio.objects.count())
        self.assertEqual(data["total_genres"], Genre.objects.count())

        attendu_genres = list(
            Genre.objects.annotate(count=Count("media_items", distinct=True))
            .filter(count__gt=0)
            .order_by("-count", "name")
            .values("name", "count")
        )
        self.assertEqual(data["genre_distribution"], attendu_genres)

        attendu_annees = [
            {"year": ligne["season_year"], "count": ligne["count"]}
            for ligne in Media.objects.exclude(season_year__isnull=True)
            .values("season_year")
            .annotate(count=Count("id"))
            .order_by("season_year")
        ]
        self.assertEqual(data["works_by_year"], attendu_annees)

        self.assertEqual(
            [item["id"] for item in data["top_popular"]],
            list(
                Media.objects.exclude(popularity__isnull=True)
                .order_by("-popularity")
                .values_list("id", flat=True)[:10]
            ),
        )
        self.assertEqual(
            [item["id"] for item in data["top_rated"]],
            list(
                Media.objects.exclude(average_score__isnull=True)
                .order_by("-average_score")
                .values_list("id", flat=True)[:10]
            ),
        )

        filtre = Q(
            media_links__is_main=True,
            media_links__media__media_type="ANIME",
        )
        attendu_studios = list(
            Studio.objects.filter(filtre)
            .annotate(
                anime_count=Count("media_links", filter=filtre, distinct=True)
            )
            .filter(anime_count__gt=0)
            .order_by("-anime_count", "name")
            .values("name", "anime_count")[:10]
        )
        self.assertEqual(data["anime_by_studio"], attendu_studios)
        self.assertIn("generated_at", data)

    def test_genre_distribution_sans_compte_zero(self):
        data = get_dashboard_data()
        self.assertTrue(all(g["count"] > 0 for g in data["genre_distribution"]))
        noms = {g["name"] for g in data["genre_distribution"]}
        self.assertNotIn("Orphelin", noms)

    def test_anime_by_studio_filtre_is_main_et_anime(self):
        data = get_dashboard_data()
        noms = {s["name"]: s["anime_count"] for s in data["anime_by_studio"]}
        self.assertEqual(noms.get("MAPPA"), 2)
        self.assertNotIn("Aniplex", noms)
        self.assertNotIn("Shueisha", noms)


class DashboardVuesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Media.objects.create(
            anilist_id=1,
            title_romaji="Solo",
            media_type="ANIME",
            season_year=2023,
            popularity=10,
            average_score=70,
        )

    def setUp(self):
        self.client = Client()

    def test_racine_redirige_vers_stats(self):
        reponse = self.client.get("/")
        self.assertRedirects(
            reponse, "/stats/", status_code=302, target_status_code=200
        )

    def test_page_html_200_sans_auth(self):
        reponse = self.client.get(reverse("stats-dashboard"))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "counter-anime")
        self.assertContains(reponse, "chart-genres")
        self.assertContains(reponse, "chart-years")
        self.assertContains(reponse, "chart-studios")
        self.assertContains(reponse, "chart.js")
        self.assertContains(reponse, "bootstrap")
        self.assertContains(reponse, "font-awesome")

    def test_identite_publique_sans_reference_scolaire(self):
        reponse = self.client.get(reverse("stats-dashboard"))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "AniList Data Platform")
        self.assertContains(reponse, "Tableau de bord AniList")
        corps = reponse.content.decode()
        self.assertNotIn("INF37407", corps)
        self.assertNotIn("TP1", corps)
        self.assertNotIn("Été 2026", corps)
        self.assertNotIn("Travail pratique", corps)

    def test_api_json_200_sans_auth_memes_valeurs(self):
        attendu = get_dashboard_data()
        reponse = self.client.get(reverse("stats-api"))
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("application/json", reponse["Content-Type"])
        corps = reponse.json()
        self.assertEqual(corps["total_anime"], attendu["total_anime"])
        self.assertEqual(corps["total_manga"], attendu["total_manga"])
        self.assertEqual(corps["total_characters"], attendu["total_characters"])
        self.assertEqual(corps["genre_distribution"], attendu["genre_distribution"])
        self.assertEqual(corps["anime_by_studio"], attendu["anime_by_studio"])
        self.assertEqual(corps["works_by_year"], attendu["works_by_year"])
