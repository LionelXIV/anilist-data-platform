"""Limitations de taux pour les endpoints d'authentification sensibles."""

from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """Brute force login : 10 tentatives / minute / IP anonyme."""

    scope = "auth_login"


class RegisterRateThrottle(AnonRateThrottle):
    """Spam d'inscription : 5 tentatives / minute / IP anonyme."""

    scope = "auth_register"
