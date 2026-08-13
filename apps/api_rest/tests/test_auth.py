"""Tests des endpoints d'authentification Token."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()


class AuthentificationAPITests(APITestCase):
    def setUp(self):
        self.url_register = reverse("auth-register")
        self.url_login = reverse("auth-login")
        self.url_logout = reverse("auth-logout")
        self.url_user = reverse("auth-user")

    def test_register_valide_cree_utilisateur_et_token(self):
        reponse = self.client.post(
            self.url_register,
            {
                "username": "alice",
                "email": "alice@example.com",
                "password": "MotDePasseFort42!",
            },
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", reponse.data)
        self.assertEqual(reponse.data["user"]["username"], "alice")

        user = User.objects.get(username="alice")
        self.assertTrue(user.check_password("MotDePasseFort42!"))
        self.assertNotEqual(user.password, "MotDePasseFort42!")
        self.assertTrue(Token.objects.filter(user=user).exists())

    def test_register_username_deja_pris(self):
        User.objects.create_user(username="alice", password="MotDePasseFort42!")
        reponse = self.client.post(
            self.url_register,
            {
                "username": "alice",
                "email": "autre@example.com",
                "password": "MotDePasseFort42!",
            },
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_mot_de_passe_faible(self):
        reponse = self.client.post(
            self.url_register,
            {"username": "bob", "password": "123"},
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_valide_retourne_token(self):
        User.objects.create_user(username="carol", password="MotDePasseFort42!")
        reponse = self.client.post(
            self.url_login,
            {"username": "carol", "password": "MotDePasseFort42!"},
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertIn("token", reponse.data)
        self.assertEqual(reponse.data["user"]["username"], "carol")

    def test_login_invalide_message_generique(self):
        User.objects.create_user(username="carol", password="MotDePasseFort42!")
        reponse = self.client.post(
            self.url_login,
            {"username": "carol", "password": "mauvais"},
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(reponse.data["detail"], "Identifiants invalides.")

    def test_profil_sans_auth_refuse(self):
        reponse = self.client.get(self.url_user)
        self.assertEqual(reponse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profil_avec_token_valide(self):
        user = User.objects.create_user(
            username="dave",
            email="dave@example.com",
            password="MotDePasseFort42!",
            first_name="Dave",
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        reponse = self.client.get(self.url_user)
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data["username"], "dave")
        self.assertEqual(reponse.data["email"], "dave@example.com")
        self.assertEqual(reponse.data["first_name"], "Dave")
        self.assertIn("date_joined", reponse.data)

    def test_patch_profil_met_a_jour_champs_autorises(self):
        user = User.objects.create_user(
            username="eve",
            email="eve@example.com",
            password="MotDePasseFort42!",
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        reponse = self.client.patch(
            self.url_user,
            {
                "email": "eve2@example.com",
                "first_name": "Eve",
                "last_name": "Test",
                "username": "hacker",
            },
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.email, "eve2@example.com")
        self.assertEqual(user.first_name, "Eve")
        self.assertEqual(user.last_name, "Test")
        self.assertEqual(user.username, "eve")

    def test_logout_revoque_le_token(self):
        user = User.objects.create_user(
            username="frank", password="MotDePasseFort42!"
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        reponse = self.client.post(self.url_logout)
        self.assertEqual(reponse.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Token.objects.filter(key=token.key).exists())

        reponse = self.client.get(self.url_user)
        self.assertEqual(reponse.status_code, status.HTTP_401_UNAUTHORIZED)
