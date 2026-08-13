"""Routes de l'API REST catalogue et authentification."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api_rest.auth_views import (
    LoginView,
    LogoutView,
    RegisterView,
    UserProfileView,
)
from apps.api_rest.views import (
    CharacterViewSet,
    GenreViewSet,
    MediaViewSet,
    StudioViewSet,
)

router = DefaultRouter()
router.register("genres", GenreViewSet, basename="genre")
router.register("studios", StudioViewSet, basename="studio")
router.register("characters", CharacterViewSet, basename="character")
router.register("media", MediaViewSet, basename="media")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/user/", UserProfileView.as_view(), name="auth-user"),
    path("", include(router.urls)),
]
