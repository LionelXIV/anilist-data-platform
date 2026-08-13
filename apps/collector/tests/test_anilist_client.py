"""Tests du client HTTP AniList : robustesse réseau et limitation de débit.

`requests.post` est systématiquement simulé et l'attente est injectée, afin que
la suite ne dépende ni du réseau ni du temps réel.
"""

from unittest import mock

import requests
from django.test import SimpleTestCase

from apps.collector import anilist_client
from apps.collector.anilist_client import (
    DEFAULT_PAGE_DELAY_SECONDS,
    MAX_WAIT_SECONDS,
    AniListClient,
    AniListHTTPError,
    AniListNetworkError,
    AniListQueryError,
    AniListRateLimitError,
)
from apps.collector.tests.factices import reponse_http

REQUETE = "query { Page { pageInfo { currentPage } } }"
CORPS_VALIDE = {"data": {"Page": {"pageInfo": {"currentPage": 1}}}}


class ClientAniListTests(SimpleTestCase):
    def setUp(self):
        self.dormir = mock.Mock()
        self.horloge = mock.Mock(return_value=1_000_000.0)
        self.client = AniListClient(
            max_attempts=3,
            sleep_function=self.dormir,
            time_function=self.horloge,
        )

    def _patcher_post(self, *reponses_ou_erreurs):
        correctif = mock.patch.object(anilist_client.requests, "post")
        poste = correctif.start()
        self.addCleanup(correctif.stop)
        if len(reponses_ou_erreurs) == 1:
            valeur = reponses_ou_erreurs[0]
            if isinstance(valeur, Exception):
                poste.side_effect = valeur
            else:
                poste.return_value = valeur
        else:
            poste.side_effect = list(reponses_ou_erreurs)
        return poste

    # -- Cas nominal ---------------------------------------------------------

    def test_reponse_valide_retourne_les_donnees(self):
        self._patcher_post(reponse_http(corps=CORPS_VALIDE))

        donnees = self.client.execute_query(REQUETE, {"page": 1})

        self.assertEqual(donnees, CORPS_VALIDE["data"])
        self.dormir.assert_not_called()

    def test_les_variables_sont_transmises_dans_la_charge(self):
        poste = self._patcher_post(reponse_http(corps=CORPS_VALIDE))

        self.client.execute_query(REQUETE, {"page": 2, "perPage": 10})

        charge = poste.call_args.kwargs["json"]
        self.assertEqual(charge["variables"], {"page": 2, "perPage": 10})
        self.assertEqual(charge["query"], REQUETE)

    # -- Erreurs réseau ------------------------------------------------------

    def test_erreur_de_connexion_abandonnee_apres_le_nombre_de_tentatives(self):
        poste = self._patcher_post(requests.exceptions.ConnectionError("coupure"))

        with self.assertRaises(AniListNetworkError):
            self.client.execute_query(REQUETE)

        self.assertEqual(poste.call_count, 3)
        # Une attente entre chaque tentative, aucune après la dernière.
        self.assertEqual(self.dormir.call_count, 2)

    def test_delai_depasse_traite_comme_une_erreur_reseau(self):
        self._patcher_post(requests.exceptions.Timeout("trop long"))

        with self.assertRaises(AniListNetworkError):
            self.client.execute_query(REQUETE)

    def test_reprise_apres_une_erreur_reseau_isolee(self):
        poste = self._patcher_post(
            requests.exceptions.ConnectionError("coupure"),
            reponse_http(corps=CORPS_VALIDE),
        )

        donnees = self.client.execute_query(REQUETE)

        self.assertEqual(donnees, CORPS_VALIDE["data"])
        self.assertEqual(poste.call_count, 2)

    # -- Erreurs GraphQL et HTTP --------------------------------------------

    def test_erreur_graphql_dans_un_http_200_est_un_echec_non_reessaye(self):
        poste = self._patcher_post(
            reponse_http(corps={"errors": [{"message": "Champ inconnu"}], "data": None})
        )

        with self.assertRaises(AniListQueryError):
            self.client.execute_query(REQUETE)

        self.assertEqual(poste.call_count, 1)

    def test_reponse_sans_champ_data(self):
        self._patcher_post(reponse_http(corps={"autre": 1}))

        with self.assertRaises(AniListQueryError):
            self.client.execute_query(REQUETE)

    def test_json_illisible(self):
        self._patcher_post(reponse_http(json_invalide=True))

        with self.assertRaises(AniListQueryError):
            self.client.execute_query(REQUETE)

    def test_erreur_serveur_reessayee_puis_abandonnee(self):
        poste = self._patcher_post(reponse_http(status_code=503))

        with self.assertRaises(AniListHTTPError):
            self.client.execute_query(REQUETE)

        self.assertEqual(poste.call_count, 3)

    def test_erreur_client_non_reessayee(self):
        poste = self._patcher_post(reponse_http(status_code=400))

        with self.assertRaises(AniListHTTPError):
            self.client.execute_query(REQUETE)

        self.assertEqual(poste.call_count, 1)

    # -- Limitation de débit -------------------------------------------------

    def test_http_429_respecte_retry_after_puis_reessaie(self):
        poste = self._patcher_post(
            reponse_http(status_code=429, entetes={"Retry-After": "5"}),
            reponse_http(corps=CORPS_VALIDE),
        )

        donnees = self.client.execute_query(REQUETE)

        self.assertEqual(donnees, CORPS_VALIDE["data"])
        self.assertEqual(poste.call_count, 2)
        self.dormir.assert_called_once_with(5.0)

    def test_http_429_repete_abandonne_sans_boucle_infinie(self):
        poste = self._patcher_post(
            reponse_http(status_code=429, entetes={"Retry-After": "1"})
        )

        with self.assertRaises(AniListRateLimitError):
            self.client.execute_query(REQUETE)

        self.assertEqual(poste.call_count, 3)
        self.assertEqual(self.dormir.call_count, 2)

    def test_attente_plafonnee_meme_avec_un_retry_after_absurde(self):
        self._patcher_post(
            reponse_http(status_code=429, entetes={"Retry-After": "99999"}),
            reponse_http(corps=CORPS_VALIDE),
        )

        self.client.execute_query(REQUETE)

        self.dormir.assert_called_once_with(MAX_WAIT_SECONDS)

    def test_http_429_sans_retry_after_utilise_un_delai_par_defaut(self):
        self._patcher_post(
            reponse_http(status_code=429),
            reponse_http(corps=CORPS_VALIDE),
        )

        self.client.execute_query(REQUETE)

        self.assertEqual(self.dormir.call_count, 1)
        self.assertGreater(self.dormir.call_args.args[0], 0)

    def test_entetes_de_limitation_lus_correctement(self):
        self._patcher_post(
            reponse_http(
                corps=CORPS_VALIDE,
                entetes={
                    "X-RateLimit-Limit": "90",
                    "X-RateLimit-Remaining": "88",
                    "X-RateLimit-Reset": "1000060",
                },
            )
        )

        self.client.execute_query(REQUETE)

        self.assertEqual(self.client.rate_limit.limit, 90)
        self.assertEqual(self.client.rate_limit.remaining, 88)
        self.assertEqual(self.client.rate_limit.reset, 1000060)

    def test_entetes_de_limitation_absents_ne_bloquent_pas(self):
        self._patcher_post(reponse_http(corps=CORPS_VALIDE, entetes={}))

        self.client.execute_query(REQUETE)

        self.assertIsNone(self.client.rate_limit.limit)
        self.assertIsNone(self.client.rate_limit.remaining)
        self.assertIsNone(self.client.rate_limit.reset)
        self.assertEqual(
            self.client.recommended_page_delay(), DEFAULT_PAGE_DELAY_SECONDS
        )

    def test_entetes_de_limitation_invalides_ignores(self):
        self._patcher_post(
            reponse_http(
                corps=CORPS_VALIDE,
                entetes={
                    "X-RateLimit-Limit": "beaucoup",
                    "X-RateLimit-Remaining": "",
                    "X-RateLimit-Reset": None,
                },
            )
        )

        self.client.execute_query(REQUETE)

        self.assertIsNone(self.client.rate_limit.limit)
        self.assertEqual(
            self.client.recommended_page_delay(), DEFAULT_PAGE_DELAY_SECONDS
        )

    def test_mode_degrade_a_30_requetes_par_minute_respecte(self):
        self._patcher_post(
            reponse_http(corps=CORPS_VALIDE, entetes={"X-RateLimit-Limit": "30"})
        )

        self.client.execute_query(REQUETE)

        self.assertEqual(self.client.rate_limit.limit, 30)
        # 30 requêtes par minute imposent au moins 2 secondes entre deux appels.
        self.assertGreaterEqual(self.client.recommended_page_delay(), 2.0)

    def test_limite_tres_basse_allonge_la_pause_recommandee(self):
        self._patcher_post(
            reponse_http(corps=CORPS_VALIDE, entetes={"X-RateLimit-Limit": "10"})
        )

        self.client.execute_query(REQUETE)

        self.assertAlmostEqual(self.client.recommended_page_delay(), 6.3, places=2)

    def test_quota_presque_epuise_declenche_une_attente_avant_la_requete(self):
        self._patcher_post(
            reponse_http(
                corps=CORPS_VALIDE,
                entetes={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1000010"},
            ),
            reponse_http(corps=CORPS_VALIDE),
        )

        self.client.execute_query(REQUETE)
        self.dormir.assert_not_called()

        self.client.execute_query(REQUETE)
        self.dormir.assert_called_once_with(10.0)

    def test_quota_epuise_avec_reset_depasse_n_attend_pas(self):
        self._patcher_post(
            reponse_http(
                corps=CORPS_VALIDE,
                entetes={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "999000"},
            ),
            reponse_http(corps=CORPS_VALIDE),
        )

        self.client.execute_query(REQUETE)
        self.client.execute_query(REQUETE)

        self.dormir.assert_not_called()
