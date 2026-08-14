"""Réglages de production.

Ce module doit être sélectionné explicitement par la variable d'environnement
DJANGO_SETTINGS_MODULE au moment du déploiement. Il ne sert jamais par défaut.
"""

from .base import *  # noqa: F401,F403

DEBUG = False

# Reverse-proxy HTTPS (Railway) : Django doit voir la requête comme sécurisée.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies transmis uniquement en HTTPS (check --deploy W012 / W016).
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# En-têtes de durcissement applicables sans connaître le domaine TLS.
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Fichiers statiques Admin / Swagger / ReDoc derrière Gunicorn.
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Reportés (le TLS est terminé par Railway ; une redirection interne
# casserait les sondes HTTP du PaaS) :
# SECURE_SSL_REDIRECT = True
# SECURE_HSTS_SECONDS = 31536000
