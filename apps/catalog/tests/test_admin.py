"""Tests de l'administration Django du catalogue."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from apps.catalog.models import (
    Character,
    CharacterMedia,
    Genre,
    Media,
    MediaStudio,
    Studio,
)

User = get_user_model()


class CatalogueAdminAccesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="staff_catalog",
            password="test-password-not-secret",
            is_staff=True,
        )
        for codename in (
            "view_genre",
            "view_studio",
            "view_media",
            "view_character",
            "view_mediastudio",
            "view_charactermedia",
        ):
            cls.staff.user_permissions.add(
                Permission.objects.get(codename=codename)
            )

        cls.genre = Genre.objects.create(name="Action")
        cls.studio = Studio.objects.create(anilist_id=100, name="Bones")
        cls.media_anime = Media.objects.create(
            anilist_id=1,
            title_romaji="Hagane no Renkinjutsushi",
            title_english="Fullmetal Alchemist",
            media_type="ANIME",
            format="TV",
            status="FINISHED",
            season_year=2009,
            popularity=500,
        )
        cls.media_manga = Media.objects.create(
            anilist_id=2,
            title_romaji="One Piece",
            media_type="MANGA",
            format="MANGA",
            status="RELEASING",
            season_year=1997,
            popularity=900,
        )
        cls.media_anime.genres.add(cls.genre)
        MediaStudio.objects.create(
            media=cls.media_anime, studio=cls.studio, is_main=True
        )
        cls.character = Character.objects.create(
            anilist_id=10, name_full="Edward Elric", gender="Male"
        )
        CharacterMedia.objects.create(
            character=cls.character, media=cls.media_anime, role="MAIN"
        )

    def setUp(self):
        self.client = Client()

    def _urls_liste(self):
        return [
            reverse("admin:catalog_genre_changelist"),
            reverse("admin:catalog_studio_changelist"),
            reverse("admin:catalog_media_changelist"),
            reverse("admin:catalog_character_changelist"),
            reverse("admin:catalog_mediastudio_changelist"),
            reverse("admin:catalog_charactermedia_changelist"),
        ]

    def test_anonyme_redirige_vers_connexion_sur_les_listes(self):
        for url in self._urls_liste():
            with self.subTest(url=url):
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 302)
                self.assertIn("/admin/login/", reponse.url)

    def test_utilisateur_standard_non_staff_refuse_sur_admin(self):
        user = User.objects.create_user(
            username="user_lambda_admin",
            password="test-password-not-secret",
            is_staff=False,
        )
        self.client.force_login(user)
        reponse = self.client.get("/admin/")
        self.assertIn(reponse.status_code, (302, 403))
        if reponse.status_code == 302:
            self.assertIn("/admin/login/", reponse.url)

    def test_staff_accede_aux_listes_sans_erreur(self):
        self.client.force_login(self.staff)
        for url in self._urls_liste():
            with self.subTest(url=url):
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 200)

    def test_identite_admin_sans_reference_scolaire(self):
        self.client.force_login(self.staff)
        reponse = self.client.get("/admin/")
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Administration AniList")
        corps = reponse.content.decode()
        self.assertNotIn("INF37407", corps)
        self.assertNotIn("TP1", corps)

    def test_recherche_media_par_titre(self):
        self.client.force_login(self.staff)
        url = reverse("admin:catalog_media_changelist")
        reponse = self.client.get(url, {"q": "Fullmetal"})
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Hagane no Renkinjutsushi")
        self.assertNotContains(reponse, "One Piece")

    def test_filtre_media_type_anime(self):
        self.client.force_login(self.staff)
        url = reverse("admin:catalog_media_changelist")
        reponse = self.client.get(url, {"media_type__exact": "ANIME"})
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Hagane no Renkinjutsushi")
        self.assertNotContains(reponse, "One Piece")

    def test_genre_media_count_annote(self):
        self.client.force_login(self.staff)
        reponse = self.client.get(reverse("admin:catalog_genre_changelist"))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Action")

    def test_detail_media_affiche_les_inlines(self):
        self.client.force_login(self.staff)
        # Besoin aussi de change_media pour ouvrir la page de détail.
        self.staff.user_permissions.add(
            Permission.objects.get(codename="change_media")
        )
        url = reverse("admin:catalog_media_change", args=[self.media_anime.pk])
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Bones")
        self.assertContains(reponse, "Edward Elric")
