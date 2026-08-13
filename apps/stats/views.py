"""Vues publiques du tableau de bord statistiques."""

from django.shortcuts import render
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stats.services import get_dashboard_data


def dashboard(request):
    """Page HTML publique des statistiques."""
    data = get_dashboard_data()
    return render(
        request,
        "stats/dashboard.html",
        {
            "stats": data,
            # Listes destinées à json_script / Chart.js.
            "genre_distribution": data["genre_distribution"],
            "works_by_year": data["works_by_year"],
            "anime_by_studio": data["anime_by_studio"],
        },
    )


class StatsAPIView(APIView):
    """GET /api/stats/ — mêmes chiffres que la page HTML, pour le TP2."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(get_dashboard_data())
