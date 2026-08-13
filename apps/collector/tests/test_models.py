"""Tests unitaires du modèle de journalisation des collectes."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalog.models import MediaType
from apps.collector.models import FetchLog, FetchStatus


class FetchLogModelTests(TestCase):
    def test_statut_par_defaut_running(self):
        journal = FetchLog.objects.create()

        self.assertEqual(journal.status, FetchStatus.RUNNING)

    def test_compteurs_initialises_a_zero(self):
        journal = FetchLog.objects.create()

        self.assertEqual(journal.records_fetched, 0)
        self.assertEqual(journal.records_created, 0)
        self.assertEqual(journal.records_updated, 0)

    def test_media_type_nullable(self):
        journal = FetchLog.objects.create()
        journal.full_clean()

        self.assertIsNone(journal.media_type)

    def test_media_type_renseigne_accepte(self):
        journal = FetchLog.objects.create(media_type=MediaType.MANGA)
        journal.full_clean()

        self.assertEqual(journal.media_type, MediaType.MANGA)

    def test_criteria_accepte_un_dictionnaire(self):
        criteres = {"type": "ANIME", "season_year": 2024, "pages": 3}
        journal = FetchLog.objects.create(criteria=criteres)
        journal.refresh_from_db()

        self.assertEqual(journal.criteria, criteres)

    def test_statut_invalide_rejete(self):
        journal = FetchLog(status="INTERROMPU")

        with self.assertRaises(ValidationError) as contexte:
            journal.full_clean()

        self.assertIn("status", contexte.exception.message_dict)

    def test_type_media_invalide_rejete(self):
        journal = FetchLog(media_type="LIVRE_AUDIO")

        with self.assertRaises(ValidationError) as contexte:
            journal.full_clean()

        self.assertIn("media_type", contexte.exception.message_dict)

    def test_compteurs_negatifs_rejetes(self):
        for champ in ("records_fetched", "records_created", "records_updated"):
            with self.subTest(champ=champ):
                journal = FetchLog(**{champ: -1})

                with self.assertRaises(ValidationError) as contexte:
                    journal.full_clean()

                self.assertIn(champ, contexte.exception.message_dict)

    def test_str_contient_le_statut_et_la_date(self):
        journal = FetchLog.objects.create(status=FetchStatus.SUCCESS)
        representation = str(journal)

        self.assertIsInstance(representation, str)
        self.assertIn("Réussie", representation)
        self.assertIn(journal.started_at.strftime("%Y-%m-%d"), representation)

    def test_str_sur_instance_non_enregistree(self):
        representation = str(FetchLog())

        self.assertIsInstance(representation, str)
        self.assertIn("non démarrée", representation)

    def test_ordre_du_plus_recent_au_plus_ancien(self):
        premier = FetchLog.objects.create(status=FetchStatus.SUCCESS)
        second = FetchLog.objects.create(status=FetchStatus.FAILED)

        journaux = list(FetchLog.objects.all())

        self.assertEqual(journaux[0].pk, second.pk)
        self.assertEqual(journaux[1].pk, premier.pk)

    def test_valeurs_denumerations_de_statut(self):
        self.assertEqual(FetchStatus.RUNNING.value, "RUNNING")
        self.assertEqual(FetchStatus.SUCCESS.value, "SUCCESS")
        self.assertEqual(FetchStatus.PARTIAL.value, "PARTIAL")
        self.assertEqual(FetchStatus.FAILED.value, "FAILED")
