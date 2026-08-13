# AniList Data Platform

Django platform for collecting, storing and exposing AniList data through REST and GraphQL APIs.

## 1. Overview

This project pulls anime and manga metadata from the public [AniList](https://anilist.co) GraphQL API, stores it in MySQL, and exposes it through Django Admin, a documented REST API, a local read-only GraphQL API, and a statistics dashboard.

## 2. Features

- Collection from the AniList GraphQL API (pagination, rate-aware pauses)
- MySQL persistence with `utf8mb4` support for native titles
- Django Admin for catalog and collection logs
- REST API (read-focused catalogue + token-based auth endpoints)
- Local GraphQL API (queries only)
- Token authentication (Django REST Framework)
- Statistics dashboard (HTML + JSON aggregations)
- Fetch logging and idempotent upserts keyed by `anilist_id`

## 3. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.14 |
| Framework | Django 5.2 |
| REST | Django REST Framework, `drf-yasg` (Swagger / ReDoc) |
| GraphQL | Graphene-Django |
| Database | MySQL 8.x (`mysqlclient`) |
| Config | `python-decouple` (`.env`) |
| CORS | `django-cors-headers` (for future frontends) |
| Charts | Chart.js (stats page) |

## 4. Application architecture

```text
.
├── apps/
│   ├── catalog/        # Genre, Studio, Media, Character, relations
│   ├── collector/      # AniList client, services, FetchLog, fetch_anilist
│   ├── api_rest/       # REST viewsets, auth, filters, throttles
│   ├── api_graphql/    # Read-only Graphene schema
│   └── stats/          # HTML dashboard + /api/stats/
├── config/
│   ├── settings/       # base, development, production
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── templates/
├── manage.py
├── requirements.txt
├── .env.example
└── README.md
```

Default settings module: `config.settings.development`. For production, set `DJANGO_SETTINGS_MODULE=config.settings.production`.

## 5. Prerequisites

- Python **3.14** (`py -3.14 --version`)
- MySQL Server **8.x** (running and reachable)
- `pip` (bundled with Python)

## 6. Installation

Commands below are for Windows (`cmd.exe`). On Linux/macOS, activate the venv with `source venv/bin/activate`.

```bat
py -3.14 -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

## 7. Configuration (`.env.example`)

```bat
copy .env.example .env
```

Edit `.env` with your local values. Placeholder example (replace every value):

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
DB_NAME=anilist_data
DB_USER=anilist_user
DB_PASSWORD=choose_a_strong_password
DB_HOST=localhost
DB_PORT=3306
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

Never commit `.env`. Keep `.env.example` as the only env template in the repository.

## 8. MySQL database setup

As a MySQL administrator:

```sql
CREATE DATABASE anilist_data
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'anilist_user'@'localhost' IDENTIFIED BY 'choose_a_strong_password';

GRANT ALL PRIVILEGES ON anilist_data.* TO 'anilist_user'@'localhost';
FLUSH PRIVILEGES;
```

`utf8mb4` is required for native-script titles.

### Test database privileges

Django tests often need a separate database (typically `test_<DB_NAME>`). If `manage.py test` fails with *Access denied* / *CREATE DATABASE*, create the test database manually and use `--keepdb`:

```sql
CREATE DATABASE test_anilist_data
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON test_anilist_data.* TO 'anilist_user'@'localhost';
FLUSH PRIVILEGES;
```

```bat
python manage.py test --keepdb
```

## 9. Migrations

```bat
python manage.py migrate
```

## 10. Superuser

```bat
python manage.py createsuperuser
```

## 11. Run the server

```bat
python manage.py runserver
```

Default URL: `http://127.0.0.1:8000/`.

## 12. Data collection

Management command (network access to `graphql.anilist.co`):

```bat
python manage.py fetch_anilist --help
```

Conservative first-run example:

```bat
python manage.py fetch_anilist --type ANIME --year 2023 --max-pages 1 --per-page 10
```

Useful flags: `--type` (`ANIME` / `MANGA`), `--year`, `--genre`, `--status`, `--sort`, `--max-pages`, `--per-page`. Between pages, the client waits about 2.1 seconds. Each run writes a `FetchLog` entry; re-running the same query must not create duplicate media (`anilist_id` is unique).

## 13. Main URLs

| URL | Purpose |
|---|---|
| `/admin/` | Django administration |
| `/api/` | REST API root |
| `/api/auth/` | Register, login, logout, profile |
| `/swagger/` | Swagger UI |
| `/redoc/` | ReDoc |
| `/graphql/` | GraphQL endpoint (GraphiQL when `DEBUG=True`) |
| `/stats/` | Statistics dashboard |
| `/api/stats/` | Statistics JSON |

REST auth header: `Authorization: Token <key>`. In Swagger → **Authorize**, enter the full value including the `Token ` prefix.

## 14. Tests

```bat
python manage.py check
python manage.py test --keepdb
```

## 15. Security notes

- Secrets live only in `.env` (never in source control).
- REST writes and sensitive actions require authentication; catalogue reads are public by design.
- Login and registration are rate-limited (throttling).
- GraphQL is query-only (no mutations).
- Production settings exist under `config.settings.production`; enable HTTPS / HSTS only when you actually deploy behind TLS.
- Token auth has no built-in expiry; revoke by logging out (token deletion).

## 16. License

No license specified.
