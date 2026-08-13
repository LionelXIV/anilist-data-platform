"""Administration Django des journaux de collecte AniList.

FetchLog est consultable en lecture seule. Une seule action d'écriture
volontaire est exposée : le déclenchement d'une petite collecte de
démonstration, avec des paramètres plafonnés côté serveur.
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path
from django.utils.html import format_html

from apps.collector.models import FetchLog, FetchStatus
from apps.collector.services import fetch_and_store

# Paramètres de démonstration : jamais fournis par l'utilisateur.
ADMIN_FETCH_MEDIA_TYPE = "ANIME"
ADMIN_FETCH_MAX_PAGES = 1
ADMIN_FETCH_PER_PAGE = 10
ADMIN_FETCH_YEAR = 2023


@admin.register(FetchLog)
class FetchLogAdmin(admin.ModelAdmin):
    change_list_template = "admin/collector/fetchlog/change_list.html"

    list_display = (
        "id",
        "started_at",
        "finished_at",
        "status_badge",
        "media_type",
        "records_fetched",
        "records_created",
        "records_updated",
    )
    list_filter = ("status", "media_type")
    ordering = ("-started_at",)
    readonly_fields = (
        "started_at",
        "finished_at",
        "status",
        "media_type",
        "criteria",
        "records_fetched",
        "records_created",
        "records_updated",
        "error_message",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Autorisé pour le nettoyage des journaux de test / démonstration.
        return request.user.is_superuser

    @admin.display(description="Statut", ordering="status")
    def status_badge(self, obj):
        classes = {
            FetchStatus.SUCCESS: "bg-success",
            FetchStatus.PARTIAL: "bg-warning text-dark",
            FetchStatus.FAILED: "bg-danger",
            FetchStatus.RUNNING: "bg-info text-dark",
        }
        icons = {
            FetchStatus.SUCCESS: "fa-circle-check",
            FetchStatus.PARTIAL: "fa-triangle-exclamation",
            FetchStatus.FAILED: "fa-circle-xmark",
            FetchStatus.RUNNING: "fa-spinner",
        }
        css = classes.get(obj.status, "bg-secondary")
        icon = icons.get(obj.status, "fa-circle-info")
        libelle = obj.get_status_display() if obj.status else "—"
        return format_html(
            '<span class="badge {}">'
            '<i class="fa-solid {}" aria-hidden="true"></i> {}</span>',
            css,
            icon,
            libelle,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "trigger-fetch/",
                self.admin_site.admin_view(self.trigger_fetch_view),
                name="collector_fetchlog_trigger_fetch",
            ),
        ]
        return custom + urls

    def trigger_fetch_view(self, request):
        """Déclenche une petite collecte plafonnée, ou affiche la confirmation."""
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        if not request.user.has_perm("collector.add_fetchlog"):
            raise PermissionDenied

        if request.method == "GET":
            context = {
                **self.admin_site.each_context(request),
                "title": "Confirmer la petite collecte",
                "opts": self.model._meta,
                "media_type": ADMIN_FETCH_MEDIA_TYPE,
                "max_pages": ADMIN_FETCH_MAX_PAGES,
                "per_page": ADMIN_FETCH_PER_PAGE,
                "year": ADMIN_FETCH_YEAR,
            }
            return render(
                request,
                "admin/collector/fetchlog/trigger_confirm.html",
                context,
            )

        if request.method != "POST":
            raise PermissionDenied

        return self._executer_collecte_admin(request)

    def _executer_collecte_admin(self, request):
        try:
            journal = fetch_and_store(
                media_type=ADMIN_FETCH_MEDIA_TYPE,
                year=ADMIN_FETCH_YEAR,
                max_pages=ADMIN_FETCH_MAX_PAGES,
                per_page=ADMIN_FETCH_PER_PAGE,
            )
        except Exception:
            messages.error(
                request,
                "La collecte a échoué de façon inattendue. "
                "Consulter les journaux côté serveur si nécessaire.",
            )
            return redirect("admin:collector_fetchlog_changelist")

        detail = (
            f"FetchLog #{journal.pk} — reçus : {journal.records_fetched}, "
            f"créés : {journal.records_created}, "
            f"mis à jour : {journal.records_updated}."
        )

        if journal.status == FetchStatus.SUCCESS:
            messages.success(request, f"Collecte réussie. {detail}")
        elif journal.status == FetchStatus.PARTIAL:
            messages.warning(
                request,
                f"Collecte partielle : une partie des données a échoué. {detail}",
            )
        else:
            messages.error(request, f"Collecte échouée. {detail}")

        return redirect("admin:collector_fetchlog_changelist")
