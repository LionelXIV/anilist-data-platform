"""Modèles du collecteur : journalisation des opérations de récupération AniList.

L'ancien TP1 ne conservait aucune trace de ses moissonnages : la progression
n'existait que dans la session HTTP et disparaissait au redémarrage du serveur.
`FetchLog` corrige ce défaut et répond à l'exigence de l'énoncé de pouvoir
consulter les opérations de récupération depuis l'administration.
"""

from django.core.validators import MinValueValidator
from django.db import models

from apps.catalog.models import MediaType


class FetchStatus(models.TextChoices):
    """État d'une opération de collecte."""

    RUNNING = "RUNNING", "En cours"
    SUCCESS = "SUCCESS", "Réussie"
    PARTIAL = "PARTIAL", "Partielle"
    FAILED = "FAILED", "Échouée"


class FetchLog(models.Model):
    """Journal d'une opération de collecte auprès de l'API AniList."""

    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Démarrée le")
    finished_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Terminée le"
    )
    status = models.CharField(
        max_length=10,
        choices=FetchStatus.choices,
        default=FetchStatus.RUNNING,
        db_index=True,
        verbose_name="Statut",
    )
    # Nullable pour permettre une opération portant sur plusieurs types à la fois.
    media_type = models.CharField(
        max_length=10,
        choices=MediaType.choices,
        blank=True,
        null=True,
        verbose_name="Type d'œuvre",
    )
    criteria = models.JSONField(
        blank=True, null=True, verbose_name="Critères de collecte"
    )
    records_fetched = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Enregistrements récupérés",
    )
    records_created = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Enregistrements créés",
    )
    records_updated = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Enregistrements mis à jour",
    )
    error_message = models.TextField(
        blank=True, null=True, verbose_name="Message d'erreur"
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Journal de collecte"
        verbose_name_plural = "Journaux de collecte"

    def __str__(self):
        horodatage = (
            self.started_at.strftime("%Y-%m-%d %H:%M")
            if self.started_at
            else "non démarrée"
        )
        return f"Collecte {self.get_status_display()} — {horodatage}"
