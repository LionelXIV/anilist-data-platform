"""Endpoints d'authentification Token.

Permissions déclarées explicitement sur chaque vue : le défaut global
IsAuthenticatedOrReadOnly ne s'applique pas ici (le profil n'est pas
une ressource anonyme en lecture).
"""

from django.contrib.auth import authenticate, get_user_model
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_rest.serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
)
from apps.api_rest.throttles import LoginRateThrottle, RegisterRateThrottle

User = get_user_model()


def _payload_utilisateur(user, token_key=None):
    data = {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        }
    }
    if token_key is not None:
        data["token"] = token_key
    return data


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RegisterRateThrottle]

    @swagger_auto_schema(
        tags=["auth"],
        request_body=RegisterSerializer,
        responses={201: "Compte créé ; jeton émis."},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            _payload_utilisateur(user, token.key),
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    @swagger_auto_schema(
        tags=["auth"],
        request_body=LoginSerializer,
        responses={200: "Jeton émis."},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Identifiants invalides."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        token, _ = Token.objects.get_or_create(user=user)
        return Response(_payload_utilisateur(user, token.key))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=["auth"],
        operation_description=(
            "Révoque le jeton courant. Aucun corps de requête ; "
            "authentification Token requise."
        ),
        request_body=None,
        responses={204: "Jeton révoqué."},
    )
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        # 204 : révocation sans corps de réponse.
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        tags=["auth"],
        responses={200: UserProfileSerializer()},
    )
    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

    @swagger_auto_schema(
        tags=["auth"],
        request_body=UserProfileUpdateSerializer,
        responses={200: UserProfileSerializer()},
    )
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserProfileSerializer(request.user).data)
