"""Tests des fonctions de transformation, pures et sans accès à la base."""

from datetime import date

from django.test import SimpleTestCase

from apps.collector.transformers import (
    DEFAULT_SORT,
    MAX_ERROR_MESSAGE_LENGTH,
    build_query_variables,
    build_year_bounds,
    extract_character_fields,
    extract_media_fields,
    extract_studio_fields,
    normalize_genre_name,
    normalize_sort,
    parse_fuzzy_date,
    truncate_error_message,
)
from apps.collector.tests.factices import noeud_media, noeud_personnage


class DatesFloues(SimpleTestCase):
    def test_date_complete_convertie(self):
        self.assertEqual(
            parse_fuzzy_date({"year": 2009, "month": 4, "day": 5}),
            date(2009, 4, 5),
        )

    def test_annee_seule_donne_none(self):
        self.assertIsNone(parse_fuzzy_date({"year": 2009, "month": None, "day": None}))

    def test_jour_manquant_donne_none(self):
        self.assertIsNone(parse_fuzzy_date({"year": 2009, "month": 4, "day": None}))

    def test_date_impossible_donne_none_sans_exception(self):
        self.assertIsNone(parse_fuzzy_date({"year": 2009, "month": 2, "day": 30}))

    def test_mois_hors_bornes_donne_none(self):
        self.assertIsNone(parse_fuzzy_date({"year": 2009, "month": 13, "day": 1}))

    def test_entree_absente_ou_non_conforme(self):
        self.assertIsNone(parse_fuzzy_date(None))
        self.assertIsNone(parse_fuzzy_date({}))
        self.assertIsNone(parse_fuzzy_date("2009-04-05"))


class BornesAnnuelles(SimpleTestCase):
    def test_bornes_fuzzydateint(self):
        self.assertEqual(build_year_bounds(2023), (20230000, 20240000))

    def test_annee_transmise_en_chaine_acceptee(self):
        self.assertEqual(build_year_bounds("1999"), (19990000, 20000000))

    def test_annee_non_numerique_rejetee(self):
        with self.assertRaises(ValueError):
            build_year_bounds("l'an dernier")

    def test_annee_absurde_rejetee(self):
        for annee in (0, -2023, 1200, 3000):
            with self.subTest(annee=annee), self.assertRaises(ValueError):
                build_year_bounds(annee)


class VariablesDeRequete(SimpleTestCase):
    def test_variables_minimales(self):
        variables = build_query_variables(page=1, per_page=10)

        self.assertEqual(variables["page"], 1)
        self.assertEqual(variables["perPage"], 10)
        self.assertEqual(variables["type"], "ANIME")

    def test_annee_traduite_en_deux_bornes(self):
        variables = build_query_variables(page=1, per_page=10, year=2023)

        self.assertEqual(variables["yearGreater"], 20230000)
        self.assertEqual(variables["yearLesser"], 20240000)
        self.assertNotIn("seasonYear", variables)

    def test_bornes_absentes_lorsque_l_annee_n_est_pas_fournie(self):
        variables = build_query_variables(page=1, per_page=10)

        self.assertNotIn("yearGreater", variables)
        self.assertNotIn("yearLesser", variables)

    def test_genre_converti_en_liste(self):
        variables = build_query_variables(page=1, per_page=10, genre="Action")

        self.assertEqual(variables["genres"], ["Action"])

    def test_genre_absent_n_ajoute_aucune_liste_contenant_null(self):
        variables = build_query_variables(page=1, per_page=10)

        self.assertNotIn("genres", variables)

    def test_genre_vide_rejete(self):
        with self.assertRaises(ValueError):
            build_query_variables(page=1, per_page=10, genre="   ")

    def test_tri_toujours_transmis_en_liste(self):
        self.assertEqual(
            build_query_variables(page=1, per_page=10, sort="SCORE_DESC")["sort"],
            ["SCORE_DESC"],
        )

    def test_tri_par_defaut(self):
        self.assertEqual(
            build_query_variables(page=1, per_page=10)["sort"], [DEFAULT_SORT]
        )

    def test_liste_de_tris_conservee(self):
        self.assertEqual(normalize_sort(["SCORE_DESC", "ID"]), ["SCORE_DESC", "ID"])

    def test_statut_invalide_rejete(self):
        with self.assertRaises(ValueError):
            build_query_variables(page=1, per_page=10, status="TERMINE")

    def test_type_invalide_rejete(self):
        with self.assertRaises(ValueError):
            build_query_variables(page=1, per_page=10, media_type="LIGHT_NOVEL")


class ExtractionDesChamps(SimpleTestCase):
    def test_champs_media(self):
        champs = extract_media_fields(noeud_media())

        self.assertEqual(champs["title_romaji"], "Hagane no Renkinjutsushi")
        self.assertEqual(champs["title_native"], "鋼の錬金術師")
        self.assertEqual(champs["media_type"], "ANIME")
        self.assertEqual(champs["start_date"], date(2009, 4, 5))
        self.assertEqual(champs["season_year"], 2009)
        self.assertEqual(champs["average_score"], 90)
        self.assertEqual(
            champs["cover_image_url"], "https://img.anilist.co/cover1.jpg"
        )

    def test_date_partielle_dans_un_media(self):
        champs = extract_media_fields(
            noeud_media(startDate={"year": 2009, "month": None, "day": None})
        )

        self.assertIsNone(champs["start_date"])
        self.assertEqual(champs["season_year"], 2009)

    def test_titre_trop_long_tronque_plutot_que_de_perdre_l_oeuvre(self):
        champs = extract_media_fields(
            noeud_media(title={"romaji": "A" * 400, "english": None, "native": None})
        )

        self.assertEqual(len(champs["title_romaji"]), 255)

    def test_url_trop_longue_remplacee_par_none(self):
        champs = extract_media_fields(
            noeud_media(bannerImage="https://exemple.test/" + "a" * 600)
        )

        self.assertIsNone(champs["banner_image_url"])

    def test_champs_studio(self):
        champs = extract_studio_fields(
            {"id": 100, "name": "Bones", "isAnimationStudio": True}
        )

        self.assertEqual(champs, {"name": "Bones", "is_animation_studio": True})

    def test_champs_personnage(self):
        champs = extract_character_fields(noeud_personnage())

        self.assertEqual(champs["name_full"], "Edward Elric")
        self.assertEqual(champs["name_native"], "エドワード・エルリック")
        self.assertEqual(champs["age"], "15")

    def test_age_en_texte_libre_tronque_a_la_taille_de_la_colonne(self):
        champs = extract_character_fields(
            noeud_personnage(age="Inconnu, mais semble avoir la trentaine bien tassee")
        )

        self.assertLessEqual(len(champs["age"]), 50)

    def test_genre_de_personne_tronque(self):
        champs = extract_character_fields(
            noeud_personnage(gender="Non specifie dans la source originale")
        )

        self.assertLessEqual(len(champs["gender"]), 20)


class NormalisationEtTroncature(SimpleTestCase):
    def test_espaces_peripheriques_du_genre_supprimes(self):
        self.assertEqual(normalize_genre_name("  Action  "), "Action")

    def test_genre_none_donne_chaine_vide(self):
        self.assertEqual(normalize_genre_name(None), "")

    def test_message_court_inchange(self):
        self.assertEqual(truncate_error_message("Erreur breve"), "Erreur breve")

    def test_message_vide_donne_chaine_vide(self):
        self.assertEqual(truncate_error_message(None), "")

    def test_message_long_tronque_a_la_longueur_decidee(self):
        message = truncate_error_message("x" * 5000)

        self.assertEqual(len(message), MAX_ERROR_MESSAGE_LENGTH)
        self.assertTrue(message.endswith("..."))
