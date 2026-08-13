"""Tests de sécurité GraphQL.

fetchLogs protégé ; 7 autres queries publiques ; GraphiQL hors DEBUG ;
erreurs sans traceback Python ; introspection laissée active (documentée).
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token

from apps.catalog.models import Character, Genre, Media, Studio
from apps.collector.models import FetchLog, FetchStatus

User = get_user_model()

# Sept queries catalogue publiques (hors fetchLogs).
QUERIES_PUBLIQUES = (
    ("allMedia", "query { allMedia { id } }"),
    ("media", None),  # rempli dynamiquement avec un id
    ("allCharacters", "query { allCharacters { id } }"),
    ("character", None),
    ("allStudios", "query { allStudios { id } }"),
    ("studio", None),
    ("allGenres", "query { allGenres { name } }"),
)


class GraphQLSecurityBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.genre = Genre.objects.create(name="GqlSecGenre")
        cls.studio = Studio.objects.create(
            anilist_id=9101, name="GqlSecStudio", is_animation_studio=True
        )
        cls.media = Media.objects.create(
            anilist_id=9102,
            title_romaji="Gql Sec Media",
            media_type="ANIME",
            popularity=1,
        )
        cls.character = Character.objects.create(
            anilist_id=9103, name_full="Gql Sec Character"
        )
        FetchLog.objects.create(
            status=FetchStatus.SUCCESS,
            media_type="ANIME",
            records_fetched=1,
            records_created=1,
        )
        cls.user = User.objects.create_user(
            username="gql_sec", password="MotDePasseFort42!"
        )
        cls.token = Token.objects.create(user=cls.user)

    def setUp(self):
        self.client = Client()
        self.url = reverse("graphql")

    def gql(self, query, variables=None, token=None, expect_http=200):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = f"Token {token}"
        reponse = self.client.post(
            self.url,
            data=json.dumps({"query": query, "variables": variables or {}}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(reponse.status_code, expect_http)
        return reponse.json()


class FetchLogsEtQueriesPubliquesTests(GraphQLSecurityBase):
    QUERY_FETCH_LOGS = (
        "query { fetchLogs(limit: 5) { id status "
        "recordsFetched recordsCreated recordsUpdated } }"
    )

    def _assert_fetch_logs_refuse(self, data):
        self.assertIn("errors", data)
        messages = " ".join(e["message"] for e in data["errors"])
        self.assertIn("Authentification requise", messages)
        # Aucune donnée journal même partielle.
        self.assertTrue(
            data.get("data") is None or data["data"].get("fetchLogs") is None
        )

    def test_fetch_logs_protege_sans_token(self):
        """Anonyme (POST /graphql/, sans cookie ni Authorization) → refus."""
        data = self.gql(self.QUERY_FETCH_LOGS)
        self._assert_fetch_logs_refuse(data)

    def test_fetch_logs_ok_avec_token(self):
        data = self.gql(self.QUERY_FETCH_LOGS, token=self.token.key)
        self.assertNotIn("errors", data)
        journaux = data["data"]["fetchLogs"]
        self.assertGreaterEqual(len(journaux), 1)
        self.assertIn("recordsFetched", journaux[0])
        self.assertIn("recordsCreated", journaux[0])
        self.assertIn("recordsUpdated", journaux[0])

    def test_fetch_logs_refuse_jeton_invalide(self):
        data = self.gql(self.QUERY_FETCH_LOGS, token="jeton-invalide-xyz")
        self._assert_fetch_logs_refuse(data)

    def test_fetch_logs_refuse_jeton_revoque(self):
        autre = User.objects.create_user(
            username="gql_sec_revoque", password="MotDePasseFort42!"
        )
        jeton = Token.objects.create(user=autre)
        cle = jeton.key
        jeton.delete()
        data = self.gql(self.QUERY_FETCH_LOGS, token=cle)
        self._assert_fetch_logs_refuse(data)

    def test_fetch_logs_ok_avec_session(self):
        """Session Django (ex. admin connecté dans GraphiQL) → autorisé."""
        self.client.force_login(self.user)
        data = self.gql(self.QUERY_FETCH_LOGS)
        self.assertNotIn("errors", data)
        self.assertGreaterEqual(len(data["data"]["fetchLogs"]), 1)

    def test_all_genres_anonyme_toujours_accessible(self):
        data = self.gql("query { allGenres { name } }")
        self.assertNotIn("errors", data)
        self.assertIsInstance(data["data"]["allGenres"], list)

    def test_sept_autres_queries_publiques(self):
        dynamiques = {
            "media": (
                "query($id: ID!) { media(id: $id) { id } }",
                {"id": str(self.media.pk)},
            ),
            "character": (
                "query($id: ID!) { character(id: $id) { id } }",
                {"id": str(self.character.pk)},
            ),
            "studio": (
                "query($id: ID!) { studio(id: $id) { id } }",
                {"id": str(self.studio.pk)},
            ),
        }
        for nom, query in QUERIES_PUBLIQUES:
            with self.subTest(query=nom):
                if query is None:
                    query, variables = dynamiques[nom]
                else:
                    variables = None
                data = self.gql(query, variables=variables)
                self.assertNotIn("errors", data)
                self.assertIsNotNone(data.get("data"))


class GraphiQLSecurityTests(GraphQLSecurityBase):
    @override_settings(DEBUG=False)
    def test_graphiql_non_servi_si_debug_false(self):
        reponse = self.client.get(self.url, HTTP_ACCEPT="text/html")
        corps = reponse.content.decode(errors="ignore")
        self.assertNotIn("GraphiQL", corps)
        self.assertNotIn("graphiql", corps.lower())

    @override_settings(DEBUG=True)
    def test_graphiql_disponible_si_debug_true(self):
        reponse = self.client.get(self.url, HTTP_ACCEPT="text/html")
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.content.decode(errors="ignore")
        self.assertTrue(
            "GraphiQL" in corps or "graphiql" in corps.lower(),
            "GraphiQL devrait être servi lorsque DEBUG=True",
        )


class ErreursGraphQLSecurityTests(GraphQLSecurityBase):
    @override_settings(DEBUG=False)
    def test_erreur_graphql_sans_traceback_python(self):
        # graphene-django peut répondre 400 sur une requête invalide.
        reponse = self.client.post(
            self.url,
            data=json.dumps(
                {"query": "query { champInexistantSecurite { id } }"}
            ),
            content_type="application/json",
        )
        self.assertIn(reponse.status_code, (200, 400))
        data = reponse.json()
        self.assertIn("errors", data)
        texte = json.dumps(data).lower()
        self.assertNotIn("traceback", texte)
        self.assertNotIn('file "', texte)
        self.assertNotIn(".py\", line", texte)

    def test_introspection_disponible(self):
        """Introspection laissée active (schéma lecture seule, TP pédagogique)."""
        data = self.gql(
            """
            query {
              __schema {
                queryType { name }
                mutationType { name }
              }
            }
            """
        )
        self.assertNotIn("errors", data)
        self.assertEqual(data["data"]["__schema"]["queryType"]["name"], "Query")
        self.assertIsNone(data["data"]["__schema"]["mutationType"])
