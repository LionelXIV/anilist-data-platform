"""Tests du schéma OpenAPI (drf-yasg) pour les corps de requête auth."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


def _body_schema_properties(operation):
    """Extrait les clés de propriétés du paramètre body (Swagger 2.0)."""
    for param in operation.get("parameters") or []:
        if param.get("in") == "body":
            schema = param.get("schema") or {}
            # Référence $ref éventuelle résolue plus bas par l'appelant.
            return schema.get("properties") or {}, schema
    return {}, None


def _resolve_schema(schema, definitions):
    if not schema:
        return {}
    ref = schema.get("$ref")
    if ref:
        name = ref.rsplit("/", 1)[-1]
        return (definitions.get(name) or {}).get("properties") or {}
    return schema.get("properties") or {}


class SwaggerAuthRequestBodyTests(APITestCase):
    """Vérifie que Swagger documente les corps register / login / PATCH user."""

    def setUp(self):
        url = reverse("schema-json", kwargs={"format": ".json"})
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.schema = reponse.json()
        self.definitions = self.schema.get("definitions") or {}
        self.paths = self.schema.get("paths") or {}

    def _properties_for(self, path, method):
        operation = (self.paths.get(path) or {}).get(method)
        self.assertIsNotNone(
            operation,
            f"Opération {method.upper()} {path} absente du schéma Swagger",
        )
        props, raw_schema = _body_schema_properties(operation)
        if props:
            return set(props.keys())
        return set(_resolve_schema(raw_schema, self.definitions).keys())

    def test_register_request_body_documente_username_password(self):
        props = self._properties_for("/auth/register/", "post")
        self.assertIn("username", props)
        self.assertIn("password", props)
        self.assertIn("email", props)

    def test_login_request_body_documente_username_password(self):
        props = self._properties_for("/auth/login/", "post")
        self.assertIn("username", props)
        self.assertIn("password", props)

    def test_patch_user_request_body_documente_champs_profil(self):
        props = self._properties_for("/auth/user/", "patch")
        self.assertIn("email", props)
        self.assertIn("first_name", props)
        self.assertIn("last_name", props)

    def test_titre_api_professionnel(self):
        info = self.schema.get("info") or {}
        self.assertEqual(info.get("title"), "AniList Data Platform API")
        self.assertNotIn("INF37407", str(info))
        self.assertNotIn("TP1", str(info))

    def test_pages_swagger_et_redoc_sans_reference_scolaire(self):
        for nom in ("schema-swagger-ui", "schema-redoc"):
            with self.subTest(page=nom):
                reponse = self.client.get(reverse(nom))
                self.assertEqual(reponse.status_code, 200)
                corps = reponse.content.decode()
                self.assertNotIn("INF37407", corps)
                self.assertNotIn("Été 2026", corps)
