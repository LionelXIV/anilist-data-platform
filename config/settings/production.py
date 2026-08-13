"""Réglages de production.

Ce module doit être sélectionné explicitement par la variable d'environnement
DJANGO_SETTINGS_MODULE au moment du déploiement. Il ne sert jamais par défaut.
"""

from .base import *  # noqa: F401,F403

DEBUG = False

# Cookies transmis uniquement en HTTPS (check --deploy W012 / W016).
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# En-têtes de durcissement applicables sans connaître le domaine TLS.
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Reportés au déploiement réel (dépendent du certificat TLS
# et du reverse-proxy) :
# SECURE_SSL_REDIRECT = True
# SECURE_HSTS_SECONDS = 31536000
