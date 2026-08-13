"""Transformation des réponses AniList vers des valeurs prêtes pour l'ORM.

Toutes les fonctions de ce module sont pures : aucun accès à la base, aucun
appel réseau, aucun effet de bord. Elles sont donc testables sans mock HTTP.
"""

from __future__ import annotations

from datetime import date

# -- Plages acceptées pour les arguments de collecte -------------------------

MIN_YEAR = 1900
MAX_YEAR = 2100

MIN_PER_PAGE = 1
MAX_PER_PAGE = 50

MIN_MAX_PAGES = 1
MAX_MAX_PAGES = 20

MEDIA_TYPES = ("ANIME", "MANGA")

MEDIA_STATUSES = (
    "FINISHED",
    "RELEASING",
    "NOT_YET_RELEASED",
    "CANCELLED",
    "HIATUS",
)

# Sous-ensemble explicitement autorisé de l'énumération MediaSort d'AniList.
MEDIA_SORTS = (
    "POPULARITY_DESC",
    "POPULARITY",
    "SCORE_DESC",
    "SCORE",
    "TRENDING_DESC",
    "TRENDING",
    "START_DATE_DESC",
    "START_DATE",
    "FAVOURITES_DESC",
    "TITLE_ROMAJI",
    "ID",
    "ID_DESC",
)

DEFAULT_SORT = "POPULARITY_DESC"

# -- Longueurs maximales, alignées sur les modèles catalogue -----------------

LONGUEUR_TITRE = 255
LONGUEUR_NOM = 255
LONGUEUR_GENRE = 100
LONGUEUR_GENRE_PERSONNE = 20
LONGUEUR_AGE = 50
LONGUEUR_URL = 500

MAX_ERROR_MESSAGE_LENGTH = 2000


def _tronquer(valeur, longueur):
    """Coupe une chaîne trop longue pour la colonne visée.

    AniList renvoie parfois des titres, des genres ou des âges en texte libre
    plus longs que la colonne correspondante. Tronquer une seule valeur est
    préférable à rejeter l'œuvre entière au moment de `full_clean()`.
    """
    if valeur is None:
        return None
    texte = str(valeur)
    return texte if len(texte) <= longueur else texte[:longueur]


def _url_ou_none(valeur, longueur=LONGUEUR_URL):
    """Retourne l'URL, ou None si elle dépasse la colonne.

    Une URL tronquée serait invalide : mieux vaut ne rien enregistrer.
    """
    if not valeur:
        return None
    texte = str(valeur)
    return texte if len(texte) <= longueur else None


def parse_fuzzy_date(fuzzy_date):
    """Convertit une FuzzyDate AniList en `date`, ou None.

    Une date n'est construite que si l'année, le mois et le jour sont tous
    présents et forment une date réelle. Une date partielle ou impossible
    (30 février) donne None : aucun mois ni jour n'est jamais inventé.
    """
    if not isinstance(fuzzy_date, dict):
        return None

    annee = fuzzy_date.get("year")
    mois = fuzzy_date.get("month")
    jour = fuzzy_date.get("day")

    if annee is None or mois is None or jour is None:
        return None

    try:
        return date(int(annee), int(mois), int(jour))
    except (TypeError, ValueError):
        return None


def build_year_bounds(year):
    """Convertit une année en bornes FuzzyDateInt (AAAAMMJJ).

    `seasonYear` ne peut pas servir de filtre annuel autonome côté AniList :
    il exige normalement un argument `season`. Les bornes `startDate_greater`
    et `startDate_lesser` sont les arguments officiels pour un filtre par
    année seule.
    """
    try:
        annee = int(year)
    except (TypeError, ValueError) as erreur:
        raise ValueError(f"Annee invalide : {year!r}") from erreur

    if not MIN_YEAR <= annee <= MAX_YEAR:
        raise ValueError(
            f"Annee hors de la plage plausible {MIN_YEAR}-{MAX_YEAR} : {annee}"
        )

    return annee * 10000, (annee + 1) * 10000


def normalize_genre_name(nom):
    """Normalise uniquement les espaces périphériques d'un nom de genre."""
    if nom is None:
        return ""
    return _tronquer(str(nom).strip(), LONGUEUR_GENRE)


def normalize_sort(sort):
    """Retourne toujours une liste, `sort` étant de type `[MediaSort]`."""
    if sort is None:
        return [DEFAULT_SORT]
    if isinstance(sort, (list, tuple)):
        valeurs = [str(valeur) for valeur in sort if valeur]
        return valeurs or [DEFAULT_SORT]
    return [str(sort)]


def build_query_variables(
    page,
    per_page,
    media_type="ANIME",
    year=None,
    genre=None,
    status=None,
    sort=None,
):
    """Construit le dictionnaire de variables de la requête GraphQL.

    Les variables facultatives sont omises plutôt que transmises à null, et le
    genre est toujours converti en liste d'une seule chaîne : `genre_in` attend
    un `[String]`, jamais une liste contenant null.
    """
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"Type de media invalide : {media_type!r}")

    variables = {
        "page": int(page),
        "perPage": int(per_page),
        "type": media_type,
        "sort": normalize_sort(sort),
    }

    if year is not None:
        borne_inferieure, borne_superieure = build_year_bounds(year)
        variables["yearGreater"] = borne_inferieure
        variables["yearLesser"] = borne_superieure

    if genre is not None:
        nom = str(genre).strip()
        if not nom:
            raise ValueError("Le genre ne peut pas etre vide.")
        variables["genres"] = [nom]

    if status is not None:
        if status not in MEDIA_STATUSES:
            raise ValueError(f"Statut invalide : {status!r}")
        variables["status"] = status

    return variables


def extract_media_fields(brut):
    """Extrait les champs de `Media` depuis un nœud Media d'AniList."""
    titre = brut.get("title") or {}
    couverture = brut.get("coverImage") or {}

    return {
        "title_romaji": _tronquer(titre.get("romaji"), LONGUEUR_TITRE),
        "title_english": _tronquer(titre.get("english"), LONGUEUR_TITRE),
        "title_native": _tronquer(titre.get("native"), LONGUEUR_TITRE),
        "media_type": brut.get("type"),
        "format": brut.get("format"),
        "status": brut.get("status"),
        "start_date": parse_fuzzy_date(brut.get("startDate")),
        "end_date": parse_fuzzy_date(brut.get("endDate")),
        "season": brut.get("season"),
        "season_year": brut.get("seasonYear"),
        "episodes": brut.get("episodes"),
        "chapters": brut.get("chapters"),
        "volumes": brut.get("volumes"),
        "average_score": brut.get("averageScore"),
        "popularity": brut.get("popularity"),
        "cover_image_url": _url_ou_none(couverture.get("large")),
        "banner_image_url": _url_ou_none(brut.get("bannerImage")),
        "synopsis": brut.get("description"),
    }


def extract_studio_fields(noeud):
    """Extrait les champs de `Studio` depuis un nœud studio d'AniList."""
    return {
        "name": _tronquer(noeud.get("name"), LONGUEUR_NOM) or "",
        "is_animation_studio": bool(noeud.get("isAnimationStudio")),
    }


def extract_character_fields(noeud):
    """Extrait les champs de `Character` depuis un nœud personnage."""
    nom = noeud.get("name") or {}
    image = noeud.get("image") or {}

    return {
        "name_full": _tronquer(nom.get("full"), LONGUEUR_NOM),
        "name_native": _tronquer(nom.get("native"), LONGUEUR_NOM),
        "image_url": _url_ou_none(image.get("large")),
        "description": noeud.get("description"),
        "gender": _tronquer(noeud.get("gender"), LONGUEUR_GENRE_PERSONNE),
        "age": _tronquer(noeud.get("age"), LONGUEUR_AGE),
    }


def truncate_error_message(message, longueur=MAX_ERROR_MESSAGE_LENGTH):
    """Borne la taille du résumé d'erreurs enregistré dans FetchLog."""
    if not message:
        return ""
    texte = str(message)
    if len(texte) <= longueur:
        return texte
    return texte[: longueur - 3] + "..."
