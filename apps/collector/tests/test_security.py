"""Tests de sécurité collector.

- Admin FetchLog : permissions non affaiblies + déclenchement POST + perm.
- Aucune surface REST/GraphQL/stats n'appelle fetch_and_store
  (frontière OS : CLI manage.py fetch_anilist uniquement hors HTTP).
"""

import json
from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.admin import (
    CharacterAdmin,
    GenreAdmin,
    MediaAdmin,
    StudioAdmin,
)
from apps.catalog.models import Character, Genre, Media, Studio
from apps.collector.admin import FetchLogAdmin
from apps.collector.models import FetchLog, FetchStatus

User = get_user_model()
CHEMIN_SERVICE_MODULE = "apps.collector.services.fetch_and_store"
CHEMIN_SERVICE_ADMIN = "apps.collector.admin.fetch_and_store"


class AdminPermissionsSecurityTests(TestCase):
    """ModelAdmins catalogue : pas d'affaiblissement des permissions Django."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="sec_admin_staff",
            password="test-password-not-secret",
            is_staff=True,
        )

    def test_catalog_admins_ne_surchargent_pas_has_permission(self):
        paires = (
            (Genre, GenreAdmin),
            (Studio, StudioAdmin),
            (Character, CharacterAdmin),
            (Media, MediaAdmin),
        )
        for modele, classe in paires:
            with self.subTest(modele=modele.__name__):
                self.assertIs(
                    classe.has_add_permission,
                    admin.ModelAdmin.has_add_permission,
                )
                self.assertIs(
                    classe.has_change_permission,
                    admin.ModelAdmin.has_change_permission,
                )
                self.assertIs(
                    classe.has_delete_permission,
                    admin.ModelAdmin.has_delete_permission,
                )
                self.assertIs(
                    classe.has_view_permission,
                    admin.ModelAdmin.has_view_permission,
                )

    def test_fetchlog_add_et_change_refuses(self):
        modele_admin = FetchLogAdmin(FetchLog, admin.site)
        request = mock.Mock(user=self.staff)
        self.assertFalse(modele_admin.has_add_permission(request))
        self.assertFalse(modele_admin.has_change_permission(request))

    def test_fetchlog_delete_reserve_au_superuser(self):
        """Stance documentée : delete autorisé seulement pour superuser (nettoyage démo)."""
        modele_admin = FetchLogAdmin(FetchLog, admin.site)
        request_staff = mock.Mock(user=self.staff)
        self.assertFalse(modele_admin.has_delete_permission(request_staff))

        superuser = User.objects.create_superuser(
            username="sec_admin_super",
            email="sec_admin_super@example.com",
            password="test-password-not-secret",
        )
        request_super = mock.Mock(user=superuser)
        self.assertTrue(modele_admin.has_delete_permission(request_super))


class AdminFetchRegressionSecurityTests(TestCase):
    """Collecte admin : collector.add_fetchlog + POST uniquement."""

    @classmethod
    def setUpTestData(cls):
        cls.autorise = User.objects.create_user(
            username="sec_fetch_ok",
            password="test-password-not-secret",
            is_staff=True,
        )
        cls.autorise.user_permissions.add(
            Permission.objects.get(codename="view_fetchlog"),
            Permission.objects.get(codename="add_fetchlog"),
        )
        cls.sans_perm = User.objects.create_user(
            username="sec_fetch_ko",
            password="test-password-not-secret",
            is_staff=True,
        )
        cls.sans_perm.user_permissions.add(
            Permission.objects.get(codename="view_fetchlog")
        )

    def setUp(self):
        self.client = Client()
        self.url = reverse("admin:collector_fetchlog_trigger_fetch")

    def test_get_ne_declenche_pas(self):
        self.client.force_login(self.autorise)
        with mock.patch(CHEMIN_SERVICE_ADMIN) as service:
            reponse = self.client.get(self.url)
        self.assertEqual(reponse.status_code, 200)
        service.assert_not_called()

    def test_post_sans_permission_403(self):
        self.client.force_login(self.sans_perm)
        with mock.patch(CHEMIN_SERVICE_ADMIN) as service:
            reponse = self.client.post(self.url)
        self.assertEqual(reponse.status_code, 403)
        service.assert_not_called()

    def test_post_avec_permission_appelle_service(self):
        journal = FetchLog.objects.create(
            status=FetchStatus.SUCCESS,
            media_type="ANIME",
            records_fetched=1,
            records_created=1,
        )
        self.client.force_login(self.autorise)
        with mock.patch(CHEMIN_SERVICE_ADMIN, return_value=journal) as service:
            reponse = self.client.post(self.url)
        self.assertEqual(reponse.status_code, 302)
        service.assert_called_once()


class PasDeFetchViaApiSecurityTests(TestCase):
    """Aucune surface HTTP publique n'appelle fetch_and_store."""

    @classmethod
    def setUpTestData(cls):
        Genre.objects.create(name="NoFetchGenre")
        Studio.objects.create(
            anilist_id=9201, name="NoFetchStudio", is_animation_studio=True
        )
        Media.objects.create(
            anilist_id=9202,
            title_romaji="NoFetch Media",
            media_type="ANIME",
        )
        Character.objects.create(anilist_id=9203, name_full="NoFetch Char")

    @mock.patch(CHEMIN_SERVICE_MODULE)
    def test_rest_graphql_stats_napellent_pas_fetch_and_store(self, mocked):
        api = APIClient()
        for basename in ("genre", "studio", "character", "media"):
            api.get(reverse(f"{basename}-list"))
            api.post(reverse(f"{basename}-list"), {}, format="json")

        api.post(
            reverse("auth-register"),
            {
                "username": "nofetch_user",
                "email": "nofetch@example.com",
                "password": "MotDePasseFort42!",
            },
            format="json",
        )
        api.post(
            reverse("auth-login"),
            {"username": "nofetch_user", "password": "MotDePasseFort42!"},
            format="json",
        )
        api.get(reverse("auth-user"))
        api.get("/api/stats/")

        navigateur = Client()
        navigateur.get("/stats/")
        navigateur.post(
            reverse("graphql"),
            data=json.dumps({"query": "query { allMedia { id } fetchLogs { id } }"}),
            content_type="application/json",
        )
        navigateur.post(
            reverse("graphql"),
            data=json.dumps(
                {
                    "query": (
                        "mutation { fetchAndStore(mediaType: \"ANIME\") { id } }"
                    )
                }
            ),
            content_type="application/json",
        )

        mocked.assert_not_called()
