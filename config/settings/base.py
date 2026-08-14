"""
Réglages communs du projet config (TP1 INF37407, été 2026).

Ce fichier ne doit jamais être utilisé directement comme DJANGO_SETTINGS_MODULE.
Utiliser config.settings.development ou config.settings.production.

Les valeurs sensibles sont lues depuis le fichier .env, qui n'est pas versionné.
Voir .env.example pour la liste des variables attendues.
"""

from pathlib import Path

from corsheaders.defaults import default_headers
from decouple import Csv, UndefinedValueError, config

# BASE_DIR pointe sur la racine du projet, où se trouvent manage.py et .env.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# Sécurité et environnement

SECRET_KEY = config("SECRET_KEY")

DEBUG = config("DEBUG", default=False, cast=bool)


def _first_env(*names, default=None):
    """Première variable d'environnement définie (DB_* local, MYSQL* Railway)."""
    for name in names:
        try:
            value = config(name)
        except UndefinedValueError:
            continue
        if str(value) != "":
            return value
    if default is not None:
        return default
    return config(names[0])


ALLOWED_HOSTS = list(config("ALLOWED_HOSTS", default="localhost", cast=Csv()))
_railway_host = config("RAILWAY_PUBLIC_DOMAIN", default="").strip()
if _railway_host and _railway_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_railway_host)


# Applications

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "graphene_django",
    "drf_yasg",
    "corsheaders",
    "django_filters",
    "apps.catalog",
    "apps.collector",
    "apps.api_rest",
    "apps.api_graphql",
    "apps.stats",
]


# Middleware
# CorsMiddleware est placé après SecurityMiddleware et avant CommonMiddleware,
# conformément à la documentation de django-cors-headers.

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Gabarits projet (admin/base_site.html, change_list FetchLog, etc.).
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Base de données MySQL
# Le jeu de caractères utf8mb4 est requis pour les titres natifs d'AniList
# (japonais, coréen, chinois).

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": _first_env("DB_NAME", "MYSQLDATABASE"),
        "USER": _first_env("DB_USER", "MYSQLUSER"),
        "PASSWORD": _first_env("DB_PASSWORD", "MYSQLPASSWORD"),
        "HOST": _first_env("DB_HOST", "MYSQLHOST", default="localhost"),
        "PORT": _first_env("DB_PORT", "MYSQLPORT", default="3308"),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
        # Base de tests dédiée : Django ne doit jamais utiliser, vider ni recréer
        # la base principale pendant l'exécution de la suite de tests.
        "TEST": {
            "NAME": "test_inf37407_tp1_ete2026",
            "CHARSET": "utf8mb4",
            "COLLATION": "utf8mb4_unicode_ci",
        },
    }
}


# Validation des mots de passe

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Throttling ciblé — scopes utilisés par LoginRateThrottle /
    # RegisterRateThrottle. Pas de throttle global pour ne pas freiner
    # la lecture anonyme du catalogue.
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": "10/min",
        "auth_register": "5/min",
    },
}

# Documentation interactive drf-yasg.
# Dans Swagger UI, le bouton Authorize attend la valeur complète
# « Token <clé> », pas la clé seule.
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Token": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
        }
    }
}


# Graphene-Django — lecture seule, aucune mutation dans le schéma.
GRAPHENE = {
    "SCHEMA": "apps.api_graphql.schema.schema",
    "MIDDLEWARE": [],
}


# CORS
# Anticipation du TP2, qui sera une application React distincte.

CORS_ALLOWED_ORIGINS = list(
    config(
        "CORS_ALLOWED_ORIGINS",
        default="http://localhost:3000",
        cast=Csv(),
    )
)

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (*default_headers, "authorization")

CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
    if origin
]
if _railway_host:
    _railway_origin = f"https://{_railway_host}"
    if _railway_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_railway_origin)

# GraphiQL peut être activé en production (démo) sans DEBUG=True.
GRAPHENE_GRAPHIQL = config("GRAPHENE_GRAPHIQL", default=False, cast=bool)


# Internationalisation

LANGUAGE_CODE = "fr-ca"

TIME_ZONE = "America/Toronto"

USE_I18N = True

USE_TZ = True


# Fichiers statiques

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# Clé primaire par défaut

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
