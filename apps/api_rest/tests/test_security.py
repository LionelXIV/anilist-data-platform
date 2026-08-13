"""Tests de sécurité REST.

Couvre permissions catalogue/auth, throttling, CORS, validation
d'entrée et absence de traceback en production (DEBUG=False).
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.api_rest.serializers import RegisterSerializer
from apps.api_rest.throttles import LoginRateThrottle
from apps.catalog.models import Character, Genre, Media, Studio

User = get_user_model()

RESSOURCES = ("genre", "studio", "character", "media")


class PermissionsCatalogueSecurityTests(APITestCase):
    """GET anonyme OK ; POST/PUT/PATCH/DELETE → 405 sur les 4 ressources."""

    @classmethod
    def setUpTestData(cls):
        cls.genre = Genre.objects.create(name="SecGenre")
        cls.studio = Studio.objects.create(
            anilist_id=9001, name="SecStudio", is_animation_studio=True
        )
        cls.character = Character.objects.create(
            anilist_id=9002, name_full="Sec Character"
        )
        cls.media = Media.objects.create(
            anilist_id=9003,
            title_romaji="Sec Media",
            media_type="ANIME",
        )
        cls.pks = {
            "genre": cls.genre.pk,
            "studio": cls.studio.pk,
            "character": cls.character.pk,
            "media": cls.media.pk,
        }

    def test_get_list_et_retrieve_anonymes_ok(self):
        for basename in RESSOURCES:
            with self.subTest(basename=basename, action="list"):
                reponse = self.client.get(reverse(f"{basename}-list"))
                self.assertEqual(reponse.status_code, status.HTTP_200_OK)
            with self.subTest(basename=basename, action="retrieve"):
                reponse = self.client.get(
                    reverse(f"{basename}-detail", args=[self.pks[basename]])
                )
                self.assertEqual(reponse.status_code, status.HTTP_200_OK)

    def test_ecriture_405_sur_les_quatre_ressources(self):
        payload = {"name": "X"}
        for basename in RESSOURCES:
            liste = reverse(f"{basename}-list")
            detail = reverse(f"{basename}-detail", args=[self.pks[basename]])
            cas = (
                ("post", liste, payload),
                ("put", detail, payload),
                ("patch", detail, payload),
                ("delete", detail, None),
            )
            for methode, url, data in cas:
                with self.subTest(basename=basename, methode=methode):
                    kwargs = {"format": "json"}
                    if data is not None:
                        kwargs["data"] = data
                    reponse = getattr(self.client, methode)(url, **kwargs)
                    self.assertEqual(
                        reponse.status_code,
                        status.HTTP_405_METHOD_NOT_ALLOWED,
                    )


class PermissionsAuthSecurityTests(APITestCase):
    """register/login AllowAny ; logout/user exigent l'auth."""

    def setUp(self):
        self.url_register = reverse("auth-register")
        self.url_login = reverse("auth-login")
        self.url_logout = reverse("auth-logout")
        self.url_user = reverse("auth-user")

    def test_register_et_login_accessibles_sans_auth(self):
        reg = self.client.post(
            self.url_register,
            {
                "username": "sec_reg",
                "email": "sec_reg@example.com",
                "password": "MotDePasseFort42!",
            },
            format="json",
        )
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)

        User.objects.create_user(
            username="sec_login", password="MotDePasseFort42!"
        )
        login = self.client.post(
            self.url_login,
            {"username": "sec_login", "password": "MotDePasseFort42!"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_logout_et_user_401_sans_auth(self):
        self.assertEqual(
            self.client.post(self.url_logout).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client.get(self.url_user).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client.patch(
                self.url_user, {"first_name": "X"}, format="json"
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_logout_revoque_le_token(self):
        user = User.objects.create_user(
            username="sec_logout", password="MotDePasseFort42!"
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        reponse = self.client.post(self.url_logout)
        self.assertEqual(reponse.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Token.objects.filter(key=token.key).exists())
        self.assertEqual(
            self.client.get(self.url_user).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class ThrottlingSecurityTests(APITestCase):
    """Dépassement de limite → 429 (scope par IP anonyme, pas par compte).

    Le taux est forcé via patch sur la classe : DRF lit
    DEFAULT_THROTTLE_RATES une fois à l'import (THROTTLE_RATES),
    donc override_settings seul ne suffit pas en test.
    """

    def setUp(self):
        cache.clear()
        self.url_login = reverse("auth-login")
        User.objects.create_user(
            username="sec_throttle", password="MotDePasseFort42!"
        )

    def tearDown(self):
        cache.clear()

    def test_login_au_dela_de_la_limite_retourne_429(self):
        corps = {
            "username": "sec_throttle",
            "password": "mauvais-mot-de-passe",
        }
        # rate explicite (create=True : l'attribut n'existe pas sur la classe).
        with mock.patch.object(
            LoginRateThrottle, "rate", "3/min", create=True
        ):
            for _ in range(3):
                reponse = self.client.post(
                    self.url_login, corps, format="json"
                )
                self.assertIn(
                    reponse.status_code,
                    (
                        status.HTTP_400_BAD_REQUEST,
                        status.HTTP_429_TOO_MANY_REQUESTS,
                    ),
                )
            reponse = self.client.post(self.url_login, corps, format="json")
        self.assertEqual(
            reponse.status_code, status.HTTP_429_TOO_MANY_REQUESTS
        )


class CorsSecurityTests(APITestCase):
    """Origines explicites uniquement — pas de miroir pour Origin non listée."""

    @classmethod
    def setUpTestData(cls):
        Genre.objects.create(name="CorsGenre")

    @override_settings(
        CORS_ALLOWED_ORIGINS=["http://localhost:3000"],
        CORS_ALLOW_CREDENTIALS=True,
    )
    def test_origine_non_autorisee_sans_acao_correspondant(self):
        reponse = self.client.get(
            reverse("genre-list"),
            HTTP_ORIGIN="https://evil.example",
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        acao = reponse.get("Access-Control-Allow-Origin", "")
        self.assertNotEqual(acao, "https://evil.example")
        self.assertNotEqual(acao, "*")

    @override_settings(
        CORS_ALLOWED_ORIGINS=["http://localhost:3000"],
        CORS_ALLOW_CREDENTIALS=True,
    )
    def test_origine_autorisee_recoit_acao(self):
        reponse = self.client.get(
            reverse("genre-list"),
            HTTP_ORIGIN="http://localhost:3000",
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(
            reponse["Access-Control-Allow-Origin"],
            "http://localhost:3000",
        )


class ValidationEtErreursSecurityTests(APITestCase):
    def test_register_serializer_email_est_emailfield(self):
        champ = RegisterSerializer().fields["email"]
        from rest_framework import serializers

        self.assertIsInstance(champ, serializers.EmailField)

    def test_register_email_invalide_refuse(self):
        reponse = self.client.post(
            reverse("auth-register"),
            {
                "username": "sec_email",
                "email": "pas-un-email",
                "password": "MotDePasseFort42!",
            },
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", reponse.data)

    @override_settings(DEBUG=False)
    def test_404_sans_traceback_http(self):
        reponse = self.client.get("/chemin-inexistant-test-securite/")
        self.assertEqual(reponse.status_code, 404)
        corps = reponse.content.decode(errors="ignore").lower()
        self.assertNotIn("traceback", corps)
        self.assertNotIn('file "', corps)
