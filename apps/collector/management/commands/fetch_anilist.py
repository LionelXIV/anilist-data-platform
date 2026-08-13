"""Commande de collecte des œuvres depuis l'API AniList.

Exemple :

    python manage.py fetch_anilist --type ANIME --year 2023 --max-pages 1 --per-page 10

Tous les arguments sont validés contre les énumérations AniList ou des plages
sûres. Une valeur invalide interrompt la commande avec un message explicite :
aucune valeur douteuse n'est acceptée silencieusement.
"""

import argparse

from django.core.management.base import BaseCommand, CommandError

from apps.collector.models import FetchStatus
from apps.collector.services import (
    DEFAULT_MAX_PAGES,
    DEFAULT_PER_PAGE,
    fetch_and_store,
)
from apps.collector.transformers import (
    DEFAULT_SORT,
    MAX_MAX_PAGES,
    MAX_PER_PAGE,
    MAX_YEAR,
    MEDIA_SORTS,
    MEDIA_STATUSES,
    MEDIA_TYPES,
    MIN_MAX_PAGES,
    MIN_PER_PAGE,
    MIN_YEAR,
)


def _entier_dans_plage(valeur, minimum, maximum, nom):
    try:
        entier = int(valeur)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            f"{nom} doit etre un entier, valeur recue : {valeur!r}"
        )
    if not minimum <= entier <= maximum:
        raise argparse.ArgumentTypeError(
            f"{nom} doit etre compris entre {minimum} et {maximum}, "
            f"valeur recue : {entier}"
        )
    return entier


def annee_valide(valeur):
    return _entier_dans_plage(valeur, MIN_YEAR, MAX_YEAR, "--year")


def max_pages_valide(valeur):
    return _entier_dans_plage(valeur, MIN_MAX_PAGES, MAX_MAX_PAGES, "--max-pages")


def per_page_valide(valeur):
    return _entier_dans_plage(valeur, MIN_PER_PAGE, MAX_PER_PAGE, "--per-page")


def genre_valide(valeur):
    nom = str(valeur).strip()
    if not nom:
        raise argparse.ArgumentTypeError("--genre ne peut pas etre vide.")
    return nom


class Command(BaseCommand):
    help = "Collecte des oeuvres depuis l'API GraphQL AniList et les enregistre."

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            dest="media_type",
            choices=MEDIA_TYPES,
            default="ANIME",
            help="Type d'oeuvre a collecter (defaut : ANIME).",
        )
        parser.add_argument(
            "--year",
            type=annee_valide,
            default=None,
            help=(
                "Annee de debut de diffusion. Traduite en bornes FuzzyDateInt "
                f"startDate_greater/startDate_lesser ({MIN_YEAR}-{MAX_YEAR})."
            ),
        )
        parser.add_argument(
            "--genre",
            type=genre_valide,
            default=None,
            help="Genre AniList, transmis a genre_in sous forme de liste.",
        )
        parser.add_argument(
            "--status",
            choices=MEDIA_STATUSES,
            default=None,
            help="Statut AniList de l'oeuvre.",
        )
        parser.add_argument(
            "--sort",
            choices=MEDIA_SORTS,
            default=DEFAULT_SORT,
            help=f"Tri AniList, transmis en liste [MediaSort] (defaut : {DEFAULT_SORT}).",
        )
        parser.add_argument(
            "--max-pages",
            dest="max_pages",
            type=max_pages_valide,
            default=DEFAULT_MAX_PAGES,
            help=(
                "Garde-fou sur le nombre de pages parcourues "
                f"({MIN_MAX_PAGES}-{MAX_MAX_PAGES}, defaut : {DEFAULT_MAX_PAGES})."
            ),
        )
        parser.add_argument(
            "--per-page",
            dest="per_page",
            type=per_page_valide,
            default=DEFAULT_PER_PAGE,
            help=(
                "Nombre d'oeuvres par page "
                f"({MIN_PER_PAGE}-{MAX_PER_PAGE}, defaut : {DEFAULT_PER_PAGE})."
            ),
        )

    def handle(self, *args, **options):
        journal = fetch_and_store(
            media_type=options["media_type"],
            year=options["year"],
            genre=options["genre"],
            status=options["status"],
            sort=options["sort"],
            max_pages=options["max_pages"],
            per_page=options["per_page"],
        )

        self.stdout.write("")
        self.stdout.write(f"FetchLog #{journal.pk}")
        self.stdout.write(f"  Statut            : {journal.status}")
        self.stdout.write(f"  Criteres          : {journal.criteria}")
        self.stdout.write(f"  Oeuvres recues    : {journal.records_fetched}")
        self.stdout.write(f"  Oeuvres creees    : {journal.records_created}")
        self.stdout.write(f"  Oeuvres modifiees : {journal.records_updated}")

        if journal.error_message:
            self.stdout.write("  Erreurs :")
            for ligne in journal.error_message.splitlines():
                self.stdout.write(f"    - {ligne}")

        if journal.status == FetchStatus.FAILED:
            raise CommandError(
                f"La collecte a echoue (FetchLog #{journal.pk}). "
                "Consulter le champ error_message pour le detail."
            )

        if journal.status == FetchStatus.PARTIAL:
            self.stdout.write(
                self.style.WARNING("Collecte partielle : certaines oeuvres ont ete ignorees.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Collecte terminee avec succes."))
