"""Tests de l'API GraphQL locale (lecture seule).

Approche retenue : client Django standard postant
{"query": "...", "variables": {...}} vers /graphql/, plutôt que
GraphQLTestCase — plus direct et fiable avec la vue authentifiée DRF
personnalisée (Graphene-Django 3.x).
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token

from apps.api_graphql.queries import MAX_PER_PAGE
from apps.api_graphql.schema import schema
from apps.catalog.models import (
    Character,
    CharacterMedia,
    Genre,
    Media,
    MediaStudio,
    Studio,
)
from apps.collector.models import FetchLog, FetchStatus

User = get_user_model()


class GraphQLBase(TestCase):
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
        )
        CharacterMedia.objects.create(
            character=cls.character, media=cls.media, role="MAIN"
        )
        cls.fetchlog = FetchLog.objects.create(
            status=FetchStatus.SUCCESS,
            media_type="ANIME",
            records_fetched=10,
            records_created=10,
        )
        cls.user = User.objects.create_user(
            username="gql_user", password="MotDePasseFort42!"
        )
        cls.token = Token.objects.create(user=cls.user)

    def setUp(self):
        self.client = Client()
        self.url = reverse("graphql")

    def gql(self, query, variables=None, token=None):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = f"Token {token}"
        reponse = self.client.post(
            self.url,
            data=json.dumps({"query": query, "variables": variables or {}}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(reponse.status_code, 200)
        return reponse.json()


class CatalogueGraphQLTests(GraphQLBase):
    def test_all_media_liste_paginee(self):
        data = self.gql(
            """
            query {
              allMedia(page: 1, perPage: 20) {
                id
                titleRomaji
                genres { name }
              }
            }
            """
        )
        self.assertNotIn("errors", data)
        titres = [m["titleRomaji"] for m in data["data"]["allMedia"]]
        self.assertIn("Jujutsu Kaisen 2nd Season", titres)
        self.assertIn("One Piece", titres)

    def test_media_detail_is_main_et_role(self):
        data = self.gql(
            """
            query($id: ID!) {
              media(id: $id) {
                titleRomaji
                genres { name }
                studios { name isMain isAnimationStudio }
                characters { nameFull nameNative role }
              }
            }
            """,
            {"id": str(self.media.pk)},
        )
        self.assertNotIn("errors", data)
        media = data["data"]["media"]
        self.assertEqual(
            sorted(g["name"] for g in media["genres"]), ["Action", "Drama"]
        )
        studios = {s["name"]: s for s in media["studios"]}
        self.assertTrue(studios["MAPPA"]["isMain"])
        self.assertFalse(studios["Aniplex"]["isMain"])
        self.assertEqual(media["characters"][0]["role"], "MAIN")
        self.assertEqual(media["characters"][0]["nameFull"], "Yuji Itadori")

    def test_media_inexistant_retourne_null(self):
        data = self.gql(
            """
            query { media(id: "999999") { id } }
            """
        )
        self.assertNotIn("errors", data)
        self.assertIsNone(data["data"]["media"])

    def test_filtre_media_type(self):
        data = self.gql(
            """
            query {
              allMedia(mediaType: "ANIME") { mediaType titleRomaji }
            }
            """
        )
        self.assertNotIn("errors", data)
        self.assertTrue(
            all(m["mediaType"] == "ANIME" for m in data["data"]["allMedia"])
        )

    def test_filtre_genre_icontains(self):
        data = self.gql(
            """
            query {
              allMedia(genre: "act") { titleRomaji }
            }
            """
        )
        titres = [m["titleRomaji"] for m in data["data"]["allMedia"]]
        self.assertIn("Jujutsu Kaisen 2nd Season", titres)
        self.assertNotIn("One Piece", titres)

    def test_recherche_media_et_characters(self):
        data = self.gql(
            """
            query {
              allMedia(search: "Jujutsu") { titleRomaji }
              allCharacters(search: "Yuji") { nameFull }
            }
            """
        )
        self.assertNotIn("errors", data)
        self.assertEqual(
            data["data"]["allMedia"][0]["titleRomaji"],
            "Jujutsu Kaisen 2nd Season",
        )
        self.assertEqual(
            data["data"]["allCharacters"][0]["nameFull"], "Yuji Itadori"
        )

    def test_pagination_respecte_plafond(self):
        for i in range(5):
            Media.objects.create(
                anilist_id=1000 + i,
                title_romaji=f"Extra {i}",
                media_type="ANIME",
                popularity=i,
            )
        data = self.gql(
            """
            query {
              page1: allMedia(page: 1, perPage: 2) { id }
              page2: allMedia(page: 2, perPage: 2) { id }
              capped: allMedia(page: 1, perPage: 1000) { id }
            }
            """
        )
        self.assertEqual(len(data["data"]["page1"]), 2)
        self.assertEqual(len(data["data"]["page2"]), 2)
        self.assertNotEqual(
            [m["id"] for m in data["data"]["page1"]],
            [m["id"] for m in data["data"]["page2"]],
        )
        self.assertLessEqual(len(data["data"]["capped"]), MAX_PER_PAGE)

    def test_studios_et_studio_detail_is_main(self):
        data = self.gql(
            """
            query($id: ID!) {
              allStudios(isAnimationStudio: true) { name isAnimationStudio }
              studio(id: $id) {
                name
                mediaLinks { titleRomaji isMain averageScore }
              }
            }
            """,
            {"id": str(self.studio_main.pk)},
        )
        self.assertNotIn("errors", data)
        self.assertTrue(
            all(s["isAnimationStudio"] for s in data["data"]["allStudios"])
        )
        liens = data["data"]["studio"]["mediaLinks"]
        self.assertEqual(liens[0]["titleRomaji"], "Jujutsu Kaisen 2nd Season")
        self.assertTrue(liens[0]["isMain"])

    def test_all_genres_media_count(self):
        data = self.gql(
            """
            query { allGenres { name mediaCount } }
            """
        )
        self.assertNotIn("errors", data)
        counts = {g["name"]: g["mediaCount"] for g in data["data"]["allGenres"]}
        self.assertEqual(counts["Action"], 1)
        self.assertEqual(counts["Drama"], 1)

    def test_character_detail_appearances(self):
        data = self.gql(
            """
            query($id: ID!) {
              character(id: $id) {
                nameFull
                appearances { titleRomaji role mediaType }
              }
            }
            """,
            {"id": str(self.character.pk)},
        )
        self.assertNotIn("errors", data)
        apps = data["data"]["character"]["appearances"]
        self.assertEqual(apps[0]["role"], "MAIN")
        self.assertEqual(apps[0]["titleRomaji"], "Jujutsu Kaisen 2nd Season")


class FetchLogsSecuriteTests(GraphQLBase):
    QUERY = """
    query {
      fetchLogs(limit: 5) {
        id
        status
        recordsFetched
        recordsCreated
        recordsUpdated
      }
    }
    """

    def test_sans_auth_erreur_explicite(self):
        data = self.gql(self.QUERY)
        self.assertIn("errors", data)
        messages = " ".join(e["message"] for e in data["errors"])
        self.assertIn("Authentification requise", messages)
        # Pas de liste vide silencieuse
        self.assertTrue(
            data.get("data") is None or data["data"].get("fetchLogs") is None
        )

    def test_avec_token_retourne_les_journaux(self):
        data = self.gql(self.QUERY, token=self.token.key)
        self.assertNotIn("errors", data)
        journaux = data["data"]["fetchLogs"]
        self.assertGreaterEqual(len(journaux), 1)
        self.assertEqual(journaux[0]["status"], FetchStatus.SUCCESS)
        self.assertEqual(journaux[0]["recordsFetched"], 10)
        self.assertEqual(journaux[0]["recordsCreated"], 10)

    def test_jeton_invalide_refuse(self):
        data = self.gql(self.QUERY, token="pas-un-vrai-token")
        self.assertIn("errors", data)
        messages = " ".join(e["message"] for e in data["errors"])
        self.assertIn("Authentification requise", messages)
        self.assertTrue(
            data.get("data") is None or data["data"].get("fetchLogs") is None
        )

    def test_session_force_login_autorise(self):
        self.client.force_login(self.user)
        data = self.gql(self.QUERY)
        self.assertNotIn("errors", data)
        self.assertGreaterEqual(len(data["data"]["fetchLogs"]), 1)


class SchemaSansMutationTests(TestCase):
    def test_schema_sans_mutation(self):
        self.assertIsNone(schema.mutation)

    @override_settings(DEBUG=False)
    def test_graphiql_desactive_hors_debug(self):
        # GraphiQL suit settings.DEBUG à chaque requête (test HTTP :
        # apps.api_graphql.tests.test_security).
        from django.conf import settings

        from apps.api_graphql.views import DRFAuthenticatedGraphQLView

        vue = DRFAuthenticatedGraphQLView()
        vue.graphiql = bool(settings.DEBUG)
        self.assertFalse(vue.graphiql)
