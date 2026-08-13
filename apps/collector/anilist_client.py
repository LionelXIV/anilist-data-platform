"""Client HTTP pour l'API GraphQL AniList.

Ce module ne fait que communiquer avec le réseau : il ne connaît ni les modèles
Django, ni la persistance. Il gère le délai d'attente, les erreurs réseau, les
codes HTTP non conformes, les erreurs GraphQL renvoyées dans un HTTP 200, la
limitation de débit et le nombre maximal de tentatives.

Limitation de débit : la documentation AniList annonce 90 requêtes par minute,
mais l'API peut fonctionner temporairement en mode dégradé à 30 requêtes par
minute. La limite réellement applicable est publiée dans les en-têtes de
réponse. Le client les lit lorsqu'ils sont présents et exploitables, et retombe
sur une valeur conservatrice sinon. Toutes les attentes sont bornées et
injectables, afin que la suite de tests ne dorme jamais réellement.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

ANILIST_ENDPOINT = "https://graphql.anilist.co"

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_ATTEMPTS = 3

# Toute attente est plafonnée : le client ne doit jamais bloquer indéfiniment.
MAX_WAIT_SECONDS = 60.0

# Utilisé quand un HTTP 429 arrive sans en-tête Retry-After exploitable.
DEFAULT_RETRY_AFTER_SECONDS = 60.0

BACKOFF_BASE_SECONDS = 1.0

# Pause conservatrice entre deux pages : 2,1 secondes correspondent à environ
# 28 requêtes par minute, ce qui reste sous la limite dégradée de 30.
DEFAULT_PAGE_DELAY_SECONDS = 2.1
RATE_LIMIT_SAFETY_FACTOR = 1.05

# Seuil en deçà duquel le client attend la remise à zéro du quota.
LOW_REMAINING_THRESHOLD = 1

MAX_ERROR_SUMMARY_LENGTH = 300


class AniListError(Exception):
    """Erreur générique de communication avec AniList."""


class AniListNetworkError(AniListError):
    """Le serveur n'a pas pu être joint, ou le délai d'attente a expiré."""


class AniListHTTPError(AniListError):
    """Le serveur a répondu avec un code HTTP autre que 200."""


class AniListRateLimitError(AniListError):
    """La limitation de débit a été atteinte de façon répétée."""


class AniListQueryError(AniListError):
    """La réponse contient des erreurs GraphQL, ou aucun champ `data`."""


@dataclass(frozen=True)
class RateLimitInfo:
    """État de la limitation de débit tel que publié par AniList.

    Chaque champ vaut None lorsque l'en-tête correspondant est absent ou
    illisible : le client doit rester fonctionnel dans ce cas.
    """

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None


def _entier_ou_none(valeur):
    """Convertit un en-tête en entier, en tolérant l'absence et l'invalidité."""
    try:
        return int(str(valeur).strip())
    except (TypeError, ValueError):
        return None


def _resumer(texte, longueur=MAX_ERROR_SUMMARY_LENGTH):
    """Tronque un message pour ne jamais journaliser une réponse volumineuse."""
    texte = " ".join(str(texte).split())
    if len(texte) <= longueur:
        return texte
    return texte[: longueur - 1] + "…"


class AniListClient:
    """Client réutilisable pour l'API GraphQL AniList."""

    def __init__(
        self,
        endpoint=ANILIST_ENDPOINT,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        sleep_function=time.sleep,
        time_function=time.time,
        session=None,
    ):
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_attempts = max(1, int(max_attempts))
        self._dormir = sleep_function
        self._maintenant = time_function
        self._session = session
        self.rate_limit = RateLimitInfo()

    # -- Limitation de débit -------------------------------------------------

    def recommended_page_delay(self):
        """Pause à respecter entre deux pages, adaptée à la limite observée.

        Retourne au minimum la pause conservatrice par défaut. Si AniList
        annonce une limite plus basse que prévu — le mode dégradé à 30 requêtes
        par minute, par exemple — la pause est allongée en conséquence.
        """
        limite = self.rate_limit.limit
        if not limite or limite <= 0:
            return DEFAULT_PAGE_DELAY_SECONDS
        return max(
            DEFAULT_PAGE_DELAY_SECONDS,
            (60.0 / limite) * RATE_LIMIT_SAFETY_FACTOR,
        )

    def _lire_entetes(self, entetes):
        entetes = entetes or {}
        return RateLimitInfo(
            limit=_entier_ou_none(entetes.get("X-RateLimit-Limit")),
            remaining=_entier_ou_none(entetes.get("X-RateLimit-Remaining")),
            reset=_entier_ou_none(entetes.get("X-RateLimit-Reset")),
        )

    def _secondes_avant_reset(self):
        if self.rate_limit.reset is None:
            return DEFAULT_PAGE_DELAY_SECONDS
        restant = self.rate_limit.reset - self._maintenant()
        if restant <= 0:
            return 0.0
        return float(restant)

    def _attendre(self, secondes, raison):
        secondes = min(max(float(secondes), 0.0), MAX_WAIT_SECONDS)
        if secondes <= 0:
            return
        logger.info("Attente de %.1f s (%s).", secondes, raison)
        self._dormir(secondes)

    def _respecter_quota(self):
        """Attend la remise à zéro du quota lorsqu'il est presque épuisé."""
        restant = self.rate_limit.remaining
        if restant is None or restant > LOW_REMAINING_THRESHOLD:
            return
        self._attendre(self._secondes_avant_reset(), "quota bientôt épuisé")

    def _delai_retry_after(self, entetes):
        valeur = _entier_ou_none((entetes or {}).get("Retry-After"))
        if valeur is None or valeur < 0:
            return DEFAULT_RETRY_AFTER_SECONDS
        return float(valeur)

    def _delai_backoff(self, tentative):
        return BACKOFF_BASE_SECONDS * (2 ** (tentative - 1))

    # -- Requête -------------------------------------------------------------

    def execute_query(self, query, variables=None):
        """Exécute une requête GraphQL et retourne le contenu du champ `data`.

        Lève une sous-classe d'`AniListError` en cas d'échec définitif. Les
        erreurs GraphQL ne sont jamais réessayées : elles signalent un problème
        de requête, que retenter ne corrigerait pas.
        """
        charge = {"query": query, "variables": variables or {}}
        derniere_erreur = None

        for tentative in range(1, self.max_attempts + 1):
            self._respecter_quota()

            try:
                reponse = self._poster(charge)
            except requests.exceptions.RequestException as erreur:
                derniere_erreur = AniListNetworkError(
                    f"Echec reseau ({type(erreur).__name__})"
                )
                self._patienter_avant_nouvelle_tentative(
                    tentative, self._delai_backoff(tentative), "erreur reseau"
                )
                continue

            self.rate_limit = self._lire_entetes(getattr(reponse, "headers", None))

            if reponse.status_code == 429:
                derniere_erreur = AniListRateLimitError(
                    "Limite de debit atteinte (HTTP 429)"
                )
                self._patienter_avant_nouvelle_tentative(
                    tentative,
                    self._delai_retry_after(reponse.headers),
                    "HTTP 429",
                )
                continue

            if reponse.status_code >= 500:
                derniere_erreur = AniListHTTPError(
                    f"Erreur serveur AniList (HTTP {reponse.status_code})"
                )
                self._patienter_avant_nouvelle_tentative(
                    tentative, self._delai_backoff(tentative), "erreur serveur"
                )
                continue

            if reponse.status_code != 200:
                # Une erreur 4xx traduit une requête incorrecte : la réessayer
                # ne changerait rien.
                raise AniListHTTPError(
                    f"Reponse HTTP inattendue ({reponse.status_code})"
                )

            return self._extraire_donnees(reponse)

        raise derniere_erreur or AniListError("Echec de la requete AniList")

    def _poster(self, charge):
        if self._session is not None:
            return self._session.post(self.endpoint, json=charge, timeout=self.timeout)
        return requests.post(self.endpoint, json=charge, timeout=self.timeout)

    def _patienter_avant_nouvelle_tentative(self, tentative, delai, raison):
        if tentative < self.max_attempts:
            self._attendre(delai, raison)

    def _extraire_donnees(self, reponse):
        try:
            corps = reponse.json()
        except ValueError as erreur:
            raise AniListQueryError("Reponse AniList illisible (JSON invalide)") from erreur

        if not isinstance(corps, dict):
            raise AniListQueryError("Reponse AniList de forme inattendue")

        erreurs = corps.get("errors")
        if erreurs:
            raise AniListQueryError(f"Erreur GraphQL : {_resumer(self._resumer_erreurs(erreurs))}")

        donnees = corps.get("data")
        if donnees is None:
            raise AniListQueryError("Reponse AniList sans champ data")

        return donnees

    @staticmethod
    def _resumer_erreurs(erreurs):
        messages = []
        if isinstance(erreurs, list):
            for erreur in erreurs:
                if isinstance(erreur, dict):
                    messages.append(str(erreur.get("message", "erreur sans message")))
                else:
                    messages.append(str(erreur))
        else:
            messages.append(str(erreurs))
        return " | ".join(messages)


_client_par_defaut = AniListClient()


def execute_query(query, variables=None):
    """Exécute une requête avec le client partagé du module."""
    return _client_par_defaut.execute_query(query, variables)
