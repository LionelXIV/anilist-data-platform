"""Tests de l'administration FetchLog et du déclenchement sécurisé."""

from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from apps.collector.admin import (
    ADMIN_FETCH_MAX_PAGES,
    ADMIN_FETCH_MEDIA_TYPE,
    ADMIN_FETCH_PER_PAGE,
    ADMIN_FETCH_YEAR,
    FetchLogAdmin,
)
from apps.collector.models import FetchLog, FetchStatus

User = get_user_model()
CHEMIN_SERVICE = "apps.collector.admin.fetch_and_store"


def _journal(statut=FetchStatus.SUCCESS, created=3, updated=1, fetched=10):
    return FetchLog.objects.create(
        status=statut,
        media_type="ANIME",
        criteria={"source": "test"},
        records_fetched=fetched,
        records_created=created,
        records_updated=updated,
    )


class FetchLogAdminAccesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="staff_fetch",
            password="test-password-not-secret",
            is_staff=True,
        )
        cls.staff.user_permissions.add(
            Permission.objects.get(codename="view_fetchlog")
        )
        cls.journal = _journal()

    def setUp(self):
        self.client = Client()

    def test_anonyme_redirige_vers_connexion(self):
        url = reverse("admin:collector_fetchlog_changelist")
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/admin/login/", reponse.url)

    def test_staff_accede_a_la_liste(self):
        self.client.force_login(self.staff)
        reponse = self.client.get(reverse("admin:collector_fetchlog_changelist"))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, str(self.journal.pk))

    def test_filtre_par_status(self):
        _journal(statut=FetchStatus.FAILED, created=0, updated=0, fetched=0)
        self.client.force_login(self.staff)
        url = reverse("admin:collector_fetchlog_changelist")
        reponse = self.client.get(url, {"status__exact": FetchStatus.SUCCESS})
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Réussie")

    def test_has_add_permission_retourne_false(self):
        modele_admin = FetchLogAdmin(FetchLog, admin.site)
        request = mock.Mock(user=self.staff)
        self.assertFalse(modele_admin.has_add_permission(request))

    def test_url_ajout_standard_refusee(self):
        self.client.force_login(self.staff)
        self.staff.user_permissions.add(
            Permission.objects.get(codename="add_fetchlog")
        )
        reponse = self.client.get(reverse("admin:collector_fetchlog_add"))
        # Pas d'ajout manuel : redirection ou 403.
        self.assertIn(reponse.status_code, (403, 302))

    def test_champs_en_lecture_seule_sur_le_detail(self):
        modele_admin = FetchLogAdmin(FetchLog, admin.site)
        self.assertEqual(
            set(modele_admin.readonly_fields),
            {
                "started_at",
                "finished_at",
                "status",
                "media_type",
                "criteria",
                "records_fetched",
                "records_created",
                "records_updated",
                "error_message",
            },
        )

    def test_has_change_permission_retourne_false(self):
        modele_admin = FetchLogAdmin(FetchLog, admin.site)
        request = mock.Mock(user=self.staff)
        self.assertFalse(modele_admin.has_change_permission(request))

    def test_superutilisateur_peut_supprimer(self):
        superuser = User.objects.create_superuser(
            username="super_fetch",
            email="super@example.com",
            password="test-password-not-secret",
        )
        modele_admin = FetchLogAdmin(FetchLog, admin.site)
        request = mock.Mock(user=superuser)
        self.assertTrue(modele_admin.has_delete_permission(request))

    def test_staff_ordinaire_ne_peut_pas_supprimer(self):
        modele_admin = FetchLogAdmin(FetchLog, admin.site)
        request = mock.Mock(user=self.staff)
        self.assertFalse(modele_admin.has_delete_permission(request))


class DeclenchementSecuriseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.autorise = User.objects.create_user(
            username="autorise_fetch",
            password="test-password-not-secret",
            is_staff=True,
        )
        cls.autorise.user_permissions.add(
            Permission.objects.get(codename="view_fetchlog"),
            Permission.objects.get(codename="add_fetchlog"),
        )

        cls.sans_perm = User.objects.create_user(
            username="sans_perm_fetch",
            password="test-password-not-secret",
            is_staff=True,
        )
        cls.sans_perm.user_permissions.add(
            Permission.objects.get(codename="view_fetchlog")
        )

    def setUp(self):
        self.client = Client()
        self.url = reverse("admin:collector_fetchlog_trigger_fetch")

    def test_get_ne_declenche_pas_la_collecte(self):
        self.client.force_login(self.autorise)
        with mock.patch(CHEMIN_SERVICE) as service:
            reponse = self.client.get(self.url)
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "Confirmer")
        service.assert_not_called()
        # Aucun nouveau journal créé par la vue elle-même.
        self.assertEqual(FetchLog.objects.count(), 0)

    def test_anonyme_ne_peut_pas_declencher(self):
        with mock.patch(CHEMIN_SERVICE) as service:
            reponse = self.client.post(self.url)
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/admin/login/", reponse.url)
        service.assert_not_called()

    def test_staff_sans_permission_obtient_403(self):
        self.client.force_login(self.sans_perm)
        with mock.patch(CHEMIN_SERVICE) as service:
            reponse = self.client.post(self.url)
        self.assertEqual(reponse.status_code, 403)
        service.assert_not_called()

    def test_post_autorise_appelle_le_service_avec_plafonds(self):
        journal = _journal(FetchStatus.SUCCESS)
        self.client.force_login(self.autorise)
        with mock.patch(CHEMIN_SERVICE, return_value=journal) as service:
            reponse = self.client.post(self.url)

        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(
            reponse.url, reverse("admin:collector_fetchlog_changelist")
        )
        service.assert_called_once_with(
            media_type=ADMIN_FETCH_MEDIA_TYPE,
            year=ADMIN_FETCH_YEAR,
            max_pages=ADMIN_FETCH_MAX_PAGES,
            per_page=ADMIN_FETCH_PER_PAGE,
        )

    def test_message_success_pour_statut_success(self):
        journal = _journal(FetchStatus.SUCCESS, created=2, updated=0)
        self.client.force_login(self.autorise)
        with mock.patch(CHEMIN_SERVICE, return_value=journal):
            reponse = self.client.post(self.url, follow=True)

        niveaux = [m.level_tag for m in get_messages(reponse.wsgi_request)]
        self.assertIn("success", niveaux)

    def test_message_warning_pour_statut_partial(self):
        journal = _journal(FetchStatus.PARTIAL, created=1, updated=0)
        self.client.force_login(self.autorise)
        with mock.patch(CHEMIN_SERVICE, return_value=journal):
            reponse = self.client.post(self.url, follow=True)

        niveaux = [m.level_tag for m in get_messages(reponse.wsgi_request)]
        self.assertIn("warning", niveaux)

    def test_message_error_pour_statut_failed(self):
        journal = _journal(FetchStatus.FAILED, created=0, updated=0, fetched=0)
        self.client.force_login(self.autorise)
        with mock.patch(CHEMIN_SERVICE, return_value=journal):
            reponse = self.client.post(self.url, follow=True)

        niveaux = [m.level_tag for m in get_messages(reponse.wsgi_request)]
        self.assertIn("error", niveaux)

    def test_exception_du_service_produit_un_message_error(self):
        self.client.force_login(self.autorise)
        with mock.patch(CHEMIN_SERVICE, side_effect=RuntimeError("panne")):
            reponse = self.client.post(self.url, follow=True)

        msgs = list(get_messages(reponse.wsgi_request))
        niveaux = [m.level_tag for m in msgs]
        textes = " ".join(str(m) for m in msgs)
        self.assertIn("error", niveaux)
        self.assertNotIn("traceback", textes.lower())
        self.assertNotIn("panne", textes)

    def test_bouton_visible_pour_utilisateur_autorise(self):
        self.client.force_login(self.autorise)
        reponse = self.client.get(reverse("admin:collector_fetchlog_changelist"))
        self.assertContains(reponse, "Petite collecte")

    def test_bouton_absent_sans_permission_add(self):
        self.client.force_login(self.sans_perm)
        reponse = self.client.get(reverse("admin:collector_fetchlog_changelist"))
        self.assertNotContains(reponse, "Petite collecte")
