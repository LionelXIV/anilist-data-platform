"""Vue GraphQL avec authentification Token DRF + session Django.

La GraphQLView standard de graphene_django ne peuple pas request.user
via TokenAuthentication. Cette sous-classe applique le jeton DRF avant
de déléguer à Graphene, afin que info.context.user.is_authenticated
fonctionne pour fetch_logs.

Politique d'identification (session OU jeton) — documentée dans DECISIONS.md :
- pas d'en-tête Authorization → session Django (admin/GraphiQL) ou anonyme ;
- Authorization: Token <valide> → request.user = détenteur du jeton ;
- jeton présent mais invalide/révoqué → AnonymousUser (refus, pas de
  repli silencieux sur une éventuelle session).
L'autorisation de fetchLogs (staff + collector.view_fetchlog) est appliquée
dans le resolver, pas dans cette vue.

GraphiQL suit settings.DEBUG à chaque requête. csrf_exempt est appliqué
sur cette vue dans config/urls.py (client TP2 / jetons).
"""

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from graphene_django.views import GraphQLView
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class DRFAuthenticatedGraphQLView(GraphQLView):
    """GraphQLView qui authentifie l'en-tête Authorization: Token <clé>."""

    def dispatch(self, request, *args, **kwargs):
        self._appliquer_auth_drf(request)
        # GraphiQL uniquement en développement, évalué à chaque requête.
        self.graphiql = bool(settings.DEBUG)
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _appliquer_auth_drf(request):
        """Peuple request.user / request.auth depuis TokenAuthentication."""
        try:
            resultat = TokenAuthentication().authenticate(request)
        except AuthenticationFailed:
            # Jeton fourni mais invalide ou révoqué : forcer l'anonymat.
            request.user = AnonymousUser()
            request.auth = None
            return

        if resultat is not None:
            request.user, request.auth = resultat
