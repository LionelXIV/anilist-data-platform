"""Configuration des URLs du projet config (TP1 INF37407)."""

from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from apps.api_graphql.views import DRFAuthenticatedGraphQLView

admin.site.site_header = "Administration AniList"
admin.site.site_title = "Administration AniList"
admin.site.index_title = "Tableau de bord"


class ApiPrefixSchemaGenerator(OpenAPISchemaGenerator):
    """Ajoute basePath=/api pour que Swagger appelle les URLs réelles."""

    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request=request, public=public)
        schema.basePath = "/api"
        return schema


schema_view = get_schema_view(
    openapi.Info(
        title="AniList Data Platform API",
        default_version="v1",
        description=(
            "API REST de consultation du catalogue AniList et "
            "d'authentification par jeton (TokenAuthentication). "
            "Dans Swagger UI, utiliser Authorize avec la valeur "
            "« Token <clé> » (préfixe Token inclus)."
        ),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    generator_class=ApiPrefixSchemaGenerator,
    patterns=[
        path("api/", include("apps.api_rest.urls")),
    ],
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # Redirection temporaire (302) : confort navigateur ; /stats/ reste la page canonique.
    path(
        "",
        RedirectView.as_view(url="/stats/", permanent=False),
        name="root-redirect",
    ),
    path("", include("apps.stats.urls")),
    path("api/", include("apps.api_rest.urls")),
    # csrf_exempt ciblé : auth Token (TP2) et/ou session Django (GraphiQL admin).
    # GraphiQL est activé dynamiquement dans la vue lorsque DEBUG=True.
    path(
        "graphql/",
        csrf_exempt(DRFAuthenticatedGraphQLView.as_view()),
        name="graphql",
    ),
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path(
        "redoc/",
        schema_view.with_ui("redoc", cache_timeout=0),
        name="schema-redoc",
    ),
]
