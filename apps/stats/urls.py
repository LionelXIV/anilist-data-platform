"""Routes de l'application statistiques."""

from django.urls import path

from apps.stats.views import StatsAPIView, dashboard

urlpatterns = [
    path("stats/", dashboard, name="stats-dashboard"),
    path("api/stats/", StatsAPIView.as_view(), name="stats-api"),
]
