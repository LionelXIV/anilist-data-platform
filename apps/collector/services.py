"""Service de collecte : parcourt AniList et enregistre les données validées.

Trois règles structurent ce module.

D'abord, aucune sauvegarde n'a lieu sans `full_clean()` préalable. `save()` seul
n'applique ni les validateurs ni les `choices`, et `update_or_create()` écrirait
avant toute validation ; l'upsert est donc écrit à la main.

Ensuite, chaque œuvre est traitée dans sa propre transaction. L'échec d'une
œuvre — validation, intégrité, relation invalide — annule uniquement ses
écritures et laisse intactes celles des œuvres déjà traitées.

Enfin, les compteurs de `FetchLog` portent sur les œuvres, jamais sur les
entités liées : une œuvre est comptée au plus une fois, comme créée ou comme
mise à jour.
"""

from __future__ import annotations

import logging
import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import (
    Character,
    CharacterMedia,
    Genre,
    Media,
    MediaStudio,
    Studio,
)
from apps.collector.anilist_client import AniListClient, AniListError
from apps.collector.models import FetchLog, FetchStatus
from apps.collector.queries import FETCH_MEDIA_PAGE_QUERY
from apps.collector.transformers import (
    build_query_variables,
    extract_character_fields,
    extract_media_fields,
    extract_studio_fields,
    normalize_genre_name,
    normalize_sort,
    truncate_error_message,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 2
DEFAULT_PER_PAGE = 25

# Nombre d'erreurs individuelles conservées dans le résumé de FetchLog.
MAX_ERREURS_JOURNALISEES = 20
LONGUEUR_ERREUR_UNITAIRE = 200


def _resumer_erreur(prefixe, erreur):
    """Produit un message court et non sensible pour le journal de collecte."""
    detail = " ".join(str(erreur).split())
    if len(detail) > LONGUEUR_ERREUR_UNITAIRE:
        detail = detail[: LONGUEUR_ERREUR_UNITAIRE - 3] + "..."
    return f"{prefixe} : {type(erreur).__name__} — {detail}"


def _upsert_valide(modele, recherche, valeurs):
    """Crée ou met à jour une instance après validation explicite.

    Retourne `(instance, creee, modifiee)`. Une instance existante dont aucune
    valeur ne change n'est ni validée à nouveau ni réenregistrée : c'est ce qui
    permet à une relance identique de ne rien compter comme mise à jour.
    """
    instance = modele.objects.filter(**recherche).first()

    if instance is None:
        instance = modele(**recherche, **valeurs)
        instance.full_clean()
        instance.save()
        return instance, True, False

    modifiee = False
    for champ, valeur in valeurs.items():
        if getattr(instance, champ) != valeur:
            setattr(instance, champ, valeur)
            modifiee = True

    if modifiee:
        instance.full_clean()
        instance.save()

    return instance, False, modifiee


def _synchroniser_genres(media, noms_bruts):
    """Aligne les genres de l'œuvre sur la liste retournée par AniList."""
    noms = []
    for nom_brut in noms_bruts or []:
        nom = normalize_genre_name(nom_brut)
        if nom and nom not in noms:
            noms.append(nom)

    genres = []
    for nom in noms:
        genre = Genre.objects.filter(name=nom).first()
        if genre is None:
            genre = Genre(name=nom)
            genre.full_clean()
            genre.save()
        genres.append(genre)

    identifiants_actuels = set(media.genres.values_list("pk", flat=True))
    identifiants_cibles = {genre.pk for genre in genres}

    if identifiants_actuels == identifiants_cibles:
        return False

    media.genres.set(genres)
    return True


def _agreger_aretes_studios(aretes):
    """Fusionne les arêtes AniList portant sur le même studio.

    AniList renvoie parfois le même studio deux fois dans `studios.edges`,
    une fois avec `isMain=true` et une fois avec `isMain=false` (rôles
    distincts côté API). Sans agrégation, la dernière arête écraserait le
    drapeau et une relance identique compterait à tort une mise à jour.
    Un studio est principal dès qu'au moins une arête le marque comme tel.
    """
    agreges = {}
    for arete in aretes or []:
        noeud = (arete or {}).get("node") or {}
        anilist_id = noeud.get("id")
        if anilist_id is None:
            continue
        if anilist_id not in agreges:
            agreges[anilist_id] = {
                "noeud": noeud,
                "is_main": bool(arete.get("isMain")),
            }
        else:
            agreges[anilist_id]["is_main"] = agreges[anilist_id]["is_main"] or bool(
                arete.get("isMain")
            )
            # Conserve le nœud le plus informatif (nom non vide prioritaire).
            if not agreges[anilist_id]["noeud"].get("name") and noeud.get("name"):
                agreges[anilist_id]["noeud"] = noeud
    return agreges


def _synchroniser_studios(media, aretes, reponse_complete):
    """Aligne les liens œuvre-studio, `is_main` compris.

    La connexion `studios` n'est pas paginée dans notre requête et retourne en
    pratique l'ensemble des studios d'une œuvre : les liens absents de la
    réponse peuvent donc être retirés sans risque de perte silencieuse.
    """
    modifiee = False
    studios_vus = set()

    for anilist_id, info in _agreger_aretes_studios(aretes).items():
        studio, _, _ = _upsert_valide(
            Studio, {"anilist_id": anilist_id}, extract_studio_fields(info["noeud"])
        )
        studios_vus.add(studio.pk)

        _, lien_cree, lien_modifie = _upsert_valide(
            MediaStudio,
            {"media": media, "studio": studio},
            {"is_main": info["is_main"]},
        )
        if lien_cree or lien_modifie:
            modifiee = True

    if reponse_complete:
        obsoletes = media.studio_links.exclude(studio_id__in=studios_vus)
        if obsoletes.exists():
            obsoletes.delete()
            modifiee = True

    return modifiee


def _synchroniser_personnages(media, aretes):
    """Aligne les liens personnage-œuvre sur le sous-ensemble reçu.

    AniList plafonne la sous-connexion `characters` à 25 éléments par page et la
    collecte n'en parcourt qu'une seule. Le jeu reçu est donc partiel : les
    liens existants absents de ce sous-ensemble ne sont jamais supprimés, sous
    peine de perdre des personnages simplement parce qu'ils sont classés
    au-delà du 25e.
    """
    modifiee = False

    for arete in aretes or []:
        noeud = (arete or {}).get("node") or {}
        anilist_id = noeud.get("id")
        if anilist_id is None:
            continue

        personnage, _, _ = _upsert_valide(
            Character, {"anilist_id": anilist_id}, extract_character_fields(noeud)
        )

        _, lien_cree, lien_modifie = _upsert_valide(
            CharacterMedia,
            {"character": personnage, "media": media},
            {"role": arete.get("role") or None},
        )
        if lien_cree or lien_modifie:
            modifiee = True

    return modifiee


def _enregistrer_media(brut):
    """Enregistre une œuvre et ses relations. Retourne `(creee, modifiee)`."""
    anilist_id = brut.get("id")
    if anilist_id is None:
        raise ValueError("Media sans identifiant AniList")

    media, creee, modifiee = _upsert_valide(
        Media, {"anilist_id": anilist_id}, extract_media_fields(brut)
    )

    genres_modifies = _synchroniser_genres(media, brut.get("genres"))

    studios = brut.get("studios")
    studios_modifies = _synchroniser_studios(
        media,
        (studios or {}).get("edges"),
        reponse_complete=isinstance(studios, dict),
    )

    personnages_modifies = _synchroniser_personnages(
        media, (brut.get("characters") or {}).get("edges")
    )

    relations_modifiees = genres_modifies or studios_modifies or personnages_modifies
    return creee, (modifiee or relations_modifiees)


def _determiner_statut(succes, erreurs):
    """SUCCESS sans erreur, PARTIAL si succès et erreurs coexistent, sinon FAILED.

    Une page vide sans erreur reste un SUCCESS : la collecte s'est déroulée
    correctement, les critères ne correspondaient simplement à rien.
    """
    if not erreurs:
        return FetchStatus.SUCCESS
    if succes > 0:
        return FetchStatus.PARTIAL
    return FetchStatus.FAILED


def fetch_and_store(
    media_type="ANIME",
    year=None,
    genre=None,
    status=None,
    sort=None,
    max_pages=DEFAULT_MAX_PAGES,
    per_page=DEFAULT_PER_PAGE,
    client=None,
    sleep_function=time.sleep,
):
    """Collecte des œuvres AniList et les enregistre. Retourne le `FetchLog`.

    La pagination est bornée par `max_pages` et pilotée uniquement par
    `hasNextPage` : la documentation AniList signale que `total` et `lastPage`
    ne sont pas fiables actuellement.
    """
    client = client or AniListClient()

    criteres = {
        "media_type": media_type,
        "year": year,
        "genre": genre,
        "status": status,
        "sort": normalize_sort(sort),
        "max_pages": max_pages,
        "per_page": per_page,
    }

    journal = FetchLog.objects.create(media_type=media_type, criteria=criteres)

    recuperes = 0
    creees = 0
    mises_a_jour = 0
    succes = 0
    erreurs = []

    def noter(message):
        if len(erreurs) < MAX_ERREURS_JOURNALISEES:
            erreurs.append(message)

    try:
        page_courante = 1
        while page_courante <= max_pages:
            try:
                variables = build_query_variables(
                    page=page_courante,
                    per_page=per_page,
                    media_type=media_type,
                    year=year,
                    genre=genre,
                    status=status,
                    sort=sort,
                )
                donnees = client.execute_query(FETCH_MEDIA_PAGE_QUERY, variables)
            except (AniListError, ValueError) as erreur:
                noter(_resumer_erreur(f"Page {page_courante}", erreur))
                break

            page = (donnees or {}).get("Page") or {}
            medias = page.get("media") or []
            info_page = page.get("pageInfo") or {}
            recuperes += len(medias)

            for brut in medias:
                identifiant = (brut or {}).get("id")
                try:
                    with transaction.atomic():
                        creee, modifiee = _enregistrer_media(brut or {})
                except (
                    ValidationError,
                    IntegrityError,
                    ValueError,
                    TypeError,
                    KeyError,
                ) as erreur:
                    noter(_resumer_erreur(f"Media #{identifiant}", erreur))
                    continue

                succes += 1
                if creee:
                    creees += 1
                elif modifiee:
                    mises_a_jour += 1

            if not info_page.get("hasNextPage"):
                break

            page_courante += 1
            if page_courante <= max_pages:
                sleep_function(client.recommended_page_delay())

    except Exception as erreur:  # filet de sécurité : le journal doit être clos
        logger.exception("Erreur inattendue pendant la collecte AniList.")
        noter(f"Erreur inattendue : {type(erreur).__name__}")

    finally:
        journal.finished_at = timezone.now()
        journal.records_fetched = recuperes
        journal.records_created = creees
        journal.records_updated = mises_a_jour
        journal.error_message = truncate_error_message("\n".join(erreurs)) or None
        journal.status = _determiner_statut(succes, erreurs)
        journal.save(
            update_fields=[
                "finished_at",
                "records_fetched",
                "records_created",
                "records_updated",
                "error_message",
                "status",
            ]
        )

    return journal
