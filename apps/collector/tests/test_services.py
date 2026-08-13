"""Tests du service de collecte : persistance validée, relations, FetchLog."""

from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalog.models import (
    Character,
    CharacterMedia,
    Genre,
    Media,
    MediaStudio,
    Studio,
)
from apps.collector.anilist_client import AniListNetworkError, AniListQueryError
from apps.collector.models import FetchLog, FetchStatus
from apps.collector.services import fetch_and_store
from apps.collector.tests.factices import (
    ClientFactice,
    arete_personnage,
    arete_studio,
    noeud_media,
    page_media,
)
from apps.collector.transformers import MAX_ERROR_MESSAGE_LENGTH


class BaseCollecte(TestCase):
    """Outils communs : la collecte est toujours lancée sans attente réelle."""

    def collecter(self, reponses, **options):
        client = ClientFactice(reponses)
        self.dormir = mock.Mock()
        options.setdefault("max_pages", 1)
        options.setdefault("per_page", 10)
        journal = fetch_and_store(
            client=client, sleep_function=self.dormir, **options
        )
        self.client_factice = client
        return journal


class CreationEtRelations(BaseCollecte):
    def test_creation_complete_d_une_oeuvre_et_de_ses_relations(self):
        journal = self.collecter([page_media([noeud_media()])])

        media = Media.objects.get(anilist_id=1)
        self.assertEqual(media.title_romaji, "Hagane no Renkinjutsushi")
        self.assertEqual(media.title_native, "鋼の錬金術師")
        self.assertEqual(media.media_type, "ANIME")
        self.assertEqual(media.season_year, 2009)
        self.assertEqual(media.average_score, 90)

        self.assertEqual(
            sorted(media.genres.values_list("name", flat=True)),
            ["Action", "Adventure", "Drama"],
        )

        lien_studio = media.studio_links.get()
        self.assertEqual(lien_studio.studio.name, "Bones")
        self.assertTrue(lien_studio.is_main)
        self.assertTrue(lien_studio.studio.is_animation_studio)

        lien_personnage = media.character_links.get()
        self.assertEqual(lien_personnage.character.name_full, "Edward Elric")
        self.assertEqual(lien_personnage.role, "MAIN")

        self.assertEqual(journal.status, FetchStatus.SUCCESS)
        self.assertEqual(journal.records_fetched, 1)
        self.assertEqual(journal.records_created, 1)
        self.assertEqual(journal.records_updated, 0)

    def test_is_main_affecte_par_arete_et_non_par_defaut(self):
        media_brut = noeud_media(
            studios={
                "edges": [
                    arete_studio(100, "Bones", is_main=True),
                    arete_studio(101, "Aniplex", is_main=False, animation=False),
                ]
            }
        )
        self.collecter([page_media([media_brut])])

        liens = MediaStudio.objects.order_by("studio__anilist_id")
        self.assertEqual([lien.is_main for lien in liens], [True, False])
        self.assertFalse(Studio.objects.get(anilist_id=101).is_animation_studio)

    def test_role_affecte_par_arete_pour_chaque_personnage(self):
        media_brut = noeud_media(
            characters={
                "edges": [
                    arete_personnage(10, "MAIN", nom="Edward"),
                    arete_personnage(11, "SUPPORTING", nom="Winry"),
                    arete_personnage(12, "BACKGROUND", nom="Passant"),
                ]
            }
        )
        self.collecter([page_media([media_brut])])

        roles = dict(
            CharacterMedia.objects.values_list("character__anilist_id", "role")
        )
        self.assertEqual(roles, {10: "MAIN", 11: "SUPPORTING", 12: "BACKGROUND"})

    def test_genres_partages_entre_deux_oeuvres_sans_doublon(self):
        self.collecter([page_media([noeud_media(1), noeud_media(2)])])

        self.assertEqual(Genre.objects.count(), 3)
        self.assertEqual(Media.objects.count(), 2)


class Pagination(BaseCollecte):
    def test_toutes_les_pages_sont_parcourues_jusqu_a_has_next_page_faux(self):
        journal = self.collecter(
            [
                page_media([noeud_media(1)], has_next_page=True),
                page_media([noeud_media(2)], has_next_page=False),
            ],
            max_pages=5,
        )

        self.assertEqual(len(self.client_factice.appels), 2)
        self.assertEqual(journal.records_fetched, 2)
        self.assertEqual(Media.objects.count(), 2)

    def test_la_boucle_s_arrete_sur_max_pages(self):
        journal = self.collecter(
            [
                page_media([noeud_media(1)], has_next_page=True),
                page_media([noeud_media(2)], has_next_page=True),
                page_media([noeud_media(3)], has_next_page=True),
            ],
            max_pages=2,
        )

        self.assertEqual(len(self.client_factice.appels), 2)
        self.assertEqual(journal.records_fetched, 2)

    def test_pause_conservatrice_entre_deux_pages(self):
        self.collecter(
            [
                page_media([noeud_media(1)], has_next_page=True),
                page_media([noeud_media(2)], has_next_page=False),
            ],
            max_pages=5,
        )

        self.dormir.assert_called_once_with(2.1)

    def test_aucune_pause_apres_la_derniere_page(self):
        self.collecter([page_media([noeud_media(1)])], max_pages=5)

        self.dormir.assert_not_called()

    def test_numero_de_page_incremente_dans_les_variables(self):
        self.collecter(
            [
                page_media([noeud_media(1)], has_next_page=True),
                page_media([noeud_media(2)], has_next_page=False),
            ],
            max_pages=5,
        )

        self.assertEqual(
            [appel["page"] for appel in self.client_factice.appels], [1, 2]
        )


class CriteresTransmis(BaseCollecte):
    def test_annee_transmise_en_bornes_fuzzydateint(self):
        self.collecter([page_media([])], year=2023)

        variables = self.client_factice.appels[0]
        self.assertEqual(variables["yearGreater"], 20230000)
        self.assertEqual(variables["yearLesser"], 20240000)

    def test_genre_transmis_en_liste(self):
        self.collecter([page_media([])], genre="Action")

        self.assertEqual(self.client_factice.appels[0]["genres"], ["Action"])

    def test_tri_transmis_en_liste(self):
        self.collecter([page_media([])], sort="SCORE_DESC")

        self.assertEqual(self.client_factice.appels[0]["sort"], ["SCORE_DESC"])

    def test_annee_invalide_termine_la_collecte_en_echec(self):
        journal = self.collecter([page_media([])], year=1200)

        self.assertEqual(journal.status, FetchStatus.FAILED)
        self.assertEqual(len(self.client_factice.appels), 0)

    def test_criteres_enregistres_sans_donnee_sensible(self):
        journal = self.collecter(
            [page_media([])], media_type="MANGA", year=2020, genre="Drama"
        )

        self.assertEqual(
            journal.criteria,
            {
                "media_type": "MANGA",
                "year": 2020,
                "genre": "Drama",
                "status": None,
                "sort": ["POPULARITY_DESC"],
                "max_pages": 1,
                "per_page": 10,
            },
        )


class MiseAJourEtIdempotence(BaseCollecte):
    def test_relance_identique_ne_cree_ni_ne_modifie_rien(self):
        premier = self.collecter([page_media([noeud_media()])])
        second = self.collecter([page_media([noeud_media()])])

        self.assertEqual(premier.records_created, 1)
        self.assertEqual(second.records_created, 0)
        self.assertEqual(second.records_updated, 0)

        self.assertEqual(Media.objects.count(), 1)
        self.assertEqual(Genre.objects.count(), 3)
        self.assertEqual(Studio.objects.count(), 1)
        self.assertEqual(Character.objects.count(), 1)
        self.assertEqual(MediaStudio.objects.count(), 1)
        self.assertEqual(CharacterMedia.objects.count(), 1)
        self.assertEqual(FetchLog.objects.count(), 2)

    def test_modification_reelle_detectee_et_comptee_une_seule_fois(self):
        self.collecter([page_media([noeud_media()])])
        journal = self.collecter(
            [page_media([noeud_media(averageScore=85, popularity=600000)])]
        )

        self.assertEqual(journal.records_created, 0)
        self.assertEqual(journal.records_updated, 1)

        media = Media.objects.get(anilist_id=1)
        self.assertEqual(media.average_score, 85)
        self.assertEqual(media.popularity, 600000)
        self.assertEqual(Media.objects.count(), 1)

    def test_changement_de_genre_compte_comme_mise_a_jour(self):
        self.collecter([page_media([noeud_media()])])
        journal = self.collecter(
            [page_media([noeud_media(genres=["Action", "Comedy"])])]
        )

        self.assertEqual(journal.records_updated, 1)
        media = Media.objects.get(anilist_id=1)
        self.assertEqual(
            sorted(media.genres.values_list("name", flat=True)),
            ["Action", "Comedy"],
        )

    def test_changement_de_is_main_compte_comme_mise_a_jour(self):
        self.collecter([page_media([noeud_media()])])
        journal = self.collecter(
            [
                page_media(
                    [noeud_media(studios={"edges": [arete_studio(is_main=False)]})]
                )
            ]
        )

        self.assertEqual(journal.records_updated, 1)
        self.assertFalse(MediaStudio.objects.get().is_main)

    def test_studio_duplique_avec_is_main_contradictoire_conserve_le_principal(self):
        """AniList peut renvoyer le même studio deux fois (True puis False)."""
        media_brut = noeud_media(
            studios={
                "edges": [
                    arete_studio(100, "Bones", is_main=True),
                    arete_studio(101, "Aniplex", is_main=False, animation=False),
                    arete_studio(100, "Bones", is_main=False),
                ]
            }
        )
        premier = self.collecter([page_media([media_brut])])
        second = self.collecter([page_media([media_brut])])

        lien = MediaStudio.objects.get(studio__anilist_id=100)
        self.assertTrue(lien.is_main)
        self.assertEqual(MediaStudio.objects.count(), 2)
        self.assertEqual(premier.records_created, 1)
        self.assertEqual(second.records_created, 0)
        self.assertEqual(second.records_updated, 0)

    def test_lien_studio_absent_de_la_reponse_est_retire(self):
        self.collecter(
            [
                page_media(
                    [
                        noeud_media(
                            studios={
                                "edges": [arete_studio(100), arete_studio(101, "Ufotable")]
                            }
                        )
                    ]
                )
            ]
        )
        self.assertEqual(MediaStudio.objects.count(), 2)

        journal = self.collecter(
            [page_media([noeud_media(studios={"edges": [arete_studio(100)]})])]
        )

        self.assertEqual(MediaStudio.objects.count(), 1)
        self.assertEqual(journal.records_updated, 1)
        # Le studio lui-même reste en base : seul le lien a disparu.
        self.assertEqual(Studio.objects.count(), 2)

    def test_liens_de_personnages_hors_des_25_recus_ne_sont_pas_supprimes(self):
        self.collecter([page_media([noeud_media()])])
        media = Media.objects.get(anilist_id=1)

        # Personnage collecté lors d'une exécution antérieure, classé au-delà
        # du 25e dans la sous-connexion actuelle.
        ancien = Character.objects.create(anilist_id=999, name_full="Personnage rare")
        CharacterMedia.objects.create(character=ancien, media=media, role="BACKGROUND")

        journal = self.collecter([page_media([noeud_media()])])

        self.assertEqual(CharacterMedia.objects.filter(media=media).count(), 2)
        self.assertTrue(
            CharacterMedia.objects.filter(media=media, character=ancien).exists()
        )
        self.assertEqual(journal.records_updated, 0)


class ValidationEtTransactions(BaseCollecte):
    def test_score_hors_bornes_ignore_l_oeuvre_sans_arreter_la_collecte(self):
        journal = self.collecter(
            [page_media([noeud_media(1, averageScore=150), noeud_media(2)])]
        )

        self.assertEqual(journal.status, FetchStatus.PARTIAL)
        self.assertEqual(journal.records_fetched, 2)
        self.assertEqual(journal.records_created, 1)
        self.assertFalse(Media.objects.filter(anilist_id=1).exists())
        self.assertTrue(Media.objects.filter(anilist_id=2).exists())

    def test_aucune_ecriture_lorsque_full_clean_echoue(self):
        journal = self.collecter([page_media([noeud_media(averageScore=150)])])

        self.assertEqual(Media.objects.count(), 0)
        self.assertEqual(Genre.objects.count(), 0)
        self.assertEqual(Studio.objects.count(), 0)
        self.assertEqual(Character.objects.count(), 0)
        self.assertEqual(journal.status, FetchStatus.FAILED)

    def test_validation_appelee_avant_toute_sauvegarde(self):
        with mock.patch.object(
            Media, "full_clean", side_effect=ValidationError("invalide")
        ), mock.patch.object(Media, "save") as sauvegarde:
            self.collecter([page_media([noeud_media()])])

        sauvegarde.assert_not_called()

    def test_relation_invalide_annule_toutes_les_ecritures_de_l_oeuvre(self):
        media_brut = noeud_media(
            characters={"edges": [arete_personnage(10, role="PROTAGONISTE")]}
        )

        journal = self.collecter([page_media([media_brut])])

        self.assertEqual(Media.objects.count(), 0)
        self.assertEqual(Character.objects.count(), 0)
        self.assertEqual(Genre.objects.count(), 0)
        self.assertEqual(Studio.objects.count(), 0)
        self.assertEqual(journal.status, FetchStatus.FAILED)

    def test_echec_d_une_oeuvre_preserve_les_oeuvres_precedentes(self):
        media_invalide = noeud_media(
            2, characters={"edges": [arete_personnage(11, role="INVALIDE")]}
        )

        journal = self.collecter([page_media([noeud_media(1), media_invalide])])

        self.assertTrue(Media.objects.filter(anilist_id=1).exists())
        self.assertFalse(Media.objects.filter(anilist_id=2).exists())
        self.assertEqual(journal.records_created, 1)
        self.assertEqual(journal.status, FetchStatus.PARTIAL)

    def test_oeuvre_sans_identifiant_ignoree(self):
        page = page_media([noeud_media()])
        del page["Page"]["media"][0]["id"]

        journal = self.collecter([page])

        self.assertEqual(Media.objects.count(), 0)
        self.assertEqual(journal.status, FetchStatus.FAILED)


class JournalDeCollecte(BaseCollecte):
    def test_statut_success_sans_aucune_erreur(self):
        journal = self.collecter([page_media([noeud_media()])])

        self.assertEqual(journal.status, FetchStatus.SUCCESS)
        self.assertIsNone(journal.error_message)
        self.assertIsNotNone(journal.finished_at)

    def test_statut_partial_lorsque_succes_et_echec_coexistent(self):
        journal = self.collecter(
            [page_media([noeud_media(1), noeud_media(2, averageScore=150)])]
        )

        self.assertEqual(journal.status, FetchStatus.PARTIAL)
        self.assertIn("Media #2", journal.error_message)

    def test_statut_failed_lorsque_la_collecte_ne_demarre_pas(self):
        journal = self.collecter([AniListNetworkError("hote injoignable")])

        self.assertEqual(journal.status, FetchStatus.FAILED)
        self.assertEqual(journal.records_fetched, 0)
        self.assertIn("Page 1", journal.error_message)
        self.assertIsNotNone(journal.finished_at)

    def test_erreur_graphql_globale_est_un_echec(self):
        journal = self.collecter([AniListQueryError("Champ inconnu")])

        self.assertEqual(journal.status, FetchStatus.FAILED)

    def test_erreur_sur_une_page_suivante_donne_un_resultat_partiel(self):
        journal = self.collecter(
            [
                page_media([noeud_media(1)], has_next_page=True),
                AniListNetworkError("coupure"),
            ],
            max_pages=3,
        )

        self.assertEqual(journal.status, FetchStatus.PARTIAL)
        self.assertEqual(journal.records_created, 1)

    def test_page_vide_sans_erreur_reste_un_succes(self):
        journal = self.collecter([page_media([])])

        self.assertEqual(journal.status, FetchStatus.SUCCESS)
        self.assertEqual(journal.records_fetched, 0)

    def test_exception_inattendue_ne_laisse_pas_le_journal_en_cours(self):
        client = ClientFactice([])
        client.execute_query = mock.Mock(side_effect=RuntimeError("panne interne"))

        journal = fetch_and_store(
            client=client, sleep_function=mock.Mock(), max_pages=1, per_page=10
        )

        self.assertNotEqual(journal.status, FetchStatus.RUNNING)
        self.assertEqual(journal.status, FetchStatus.FAILED)
        self.assertIsNotNone(journal.finished_at)
        self.assertIn("RuntimeError", journal.error_message)

    def test_resume_d_erreurs_borne_a_la_longueur_decidee(self):
        medias = [
            noeud_media(identifiant, format="X" * 300)
            for identifiant in range(1, 26)
        ]

        journal = self.collecter([page_media(medias)])

        self.assertLessEqual(len(journal.error_message), MAX_ERROR_MESSAGE_LENGTH)
        self.assertTrue(journal.error_message.endswith("..."))
        self.assertEqual(journal.status, FetchStatus.FAILED)

    def test_un_journal_est_cree_par_execution(self):
        self.collecter([page_media([noeud_media()])])
        self.collecter([page_media([noeud_media()])])

        self.assertEqual(FetchLog.objects.count(), 2)
        self.assertEqual(Media.objects.count(), 1)

    def test_type_de_media_conserve_dans_le_journal(self):
        journal = self.collecter([page_media([])], media_type="MANGA")

        self.assertEqual(journal.media_type, "MANGA")
