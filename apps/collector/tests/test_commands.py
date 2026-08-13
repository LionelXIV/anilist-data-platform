"""Tests de la commande `fetch_anilist` : validation stricte des arguments."""

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.collector.models import FetchLog, FetchStatus

CHEMIN_SERVICE = "apps.collector.management.commands.fetch_anilist.fetch_and_store"


class ArgumentsRejetes(TestCase):
    """Aucune valeur douteuse ne doit être acceptée silencieusement."""

    def _executer(self, *arguments):
        with mock.patch(CHEMIN_SERVICE) as service:
            with self.assertRaises(CommandError):
                call_command("fetch_anilist", *arguments, stderr=StringIO())
            service.assert_not_called()

    def test_type_inconnu(self):
        self._executer("--type", "LIGHT_NOVEL")

    def test_statut_inconnu(self):
        self._executer("--status", "TERMINE")

    def test_tri_non_autorise(self):
        self._executer("--sort", "RANDOM")

    def test_max_pages_nul(self):
        self._executer("--max-pages", "0")

    def test_max_pages_negatif(self):
        self._executer("--max-pages", "-3")

    def test_max_pages_hors_plage_haute(self):
        self._executer("--max-pages", "500")

    def test_max_pages_non_numerique(self):
        self._executer("--max-pages", "beaucoup")

    def test_per_page_nul(self):
        self._executer("--per-page", "0")

    def test_per_page_au_dela_de_cinquante(self):
        self._executer("--per-page", "51")

    def test_annee_implausible(self):
        self._executer("--year", "1200")

    def test_annee_negative(self):
        self._executer("--year", "-2023")

    def test_annee_non_numerique(self):
        self._executer("--year", "recente")

    def test_genre_vide(self):
        self._executer("--genre", "   ")


class ArgumentsAcceptes(TestCase):
    def setUp(self):
        self.journal = FetchLog.objects.create(
            media_type="ANIME",
            status=FetchStatus.SUCCESS,
            criteria={"media_type": "ANIME"},
            records_fetched=10,
            records_created=10,
        )

    def test_valeurs_par_defaut(self):
        with mock.patch(CHEMIN_SERVICE, return_value=self.journal) as service:
            call_command("fetch_anilist", stdout=StringIO())

        service.assert_called_once_with(
            media_type="ANIME",
            year=None,
            genre=None,
            status=None,
            sort="POPULARITY_DESC",
            max_pages=2,
            per_page=25,
        )

    def test_arguments_complets_transmis_au_service(self):
        with mock.patch(CHEMIN_SERVICE, return_value=self.journal) as service:
            call_command(
                "fetch_anilist",
                "--type", "MANGA",
                "--year", "2023",
                "--genre", "  Action  ",
                "--status", "FINISHED",
                "--sort", "SCORE_DESC",
                "--max-pages", "1",
                "--per-page", "10",
                stdout=StringIO(),
            )

        service.assert_called_once_with(
            media_type="MANGA",
            year=2023,
            genre="Action",
            status="FINISHED",
            sort="SCORE_DESC",
            max_pages=1,
            per_page=10,
        )

    def test_resume_affiche_les_compteurs(self):
        sortie = StringIO()
        with mock.patch(CHEMIN_SERVICE, return_value=self.journal):
            call_command("fetch_anilist", stdout=sortie)

        texte = sortie.getvalue()
        self.assertIn(f"FetchLog #{self.journal.pk}", texte)
        self.assertIn("Oeuvres creees    : 10", texte)
        self.assertIn("succes", texte.lower())


class StatutFinal(TestCase):
    def test_collecte_en_echec_remonte_une_erreur_de_commande(self):
        journal = FetchLog.objects.create(
            media_type="ANIME",
            status=FetchStatus.FAILED,
            error_message="Page 1 : AniListNetworkError — hote injoignable",
        )

        with mock.patch(CHEMIN_SERVICE, return_value=journal):
            with self.assertRaises(CommandError):
                call_command("fetch_anilist", stdout=StringIO())

    def test_collecte_partielle_signalee_sans_erreur_fatale(self):
        journal = FetchLog.objects.create(
            media_type="ANIME",
            status=FetchStatus.PARTIAL,
            records_fetched=2,
            records_created=1,
            error_message="Media #2 : ValidationError — score hors bornes",
        )

        sortie = StringIO()
        with mock.patch(CHEMIN_SERVICE, return_value=journal):
            call_command("fetch_anilist", stdout=sortie)

        self.assertIn("partielle", sortie.getvalue().lower())
