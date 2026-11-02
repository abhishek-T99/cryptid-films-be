# Cryptid Films — Backend

REST API for the Cryptid Films studio site. Django + Django REST Framework,
serving the React frontend in [`cryptid-films-fe`](https://github.com/abhishek-T99/cryptid-films-fe).

| | |
|---|---|
| Python | 3.14 |
| Django | 6.1 |
| Django REST Framework | 3.18 |
| Database | SQLite (development **and** production) |

## Getting started

```bash
git clone git@github.com:abhishek-T99/cryptid-films-be.git
cd cryptid-films-be

python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash)
# .venv\Scripts\Activate.ps1       # Windows (PowerShell)
# source .venv/bin/activate        # macOS / Linux

pip install -r requirements.txt

cp .env.example .env
```

Then open `.env` and set `DJANGO_SECRET_KEY` — it has no default and the
project will not start without it:

```bash
python -c "import secrets,string;a=string.ascii_letters+string.digits;print(''.join(secrets.choice(a) for _ in range(50)))"
```

Create the database and a login for the admin:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

| URL | What it is |
|---|---|
| `http://127.0.0.1:8000/api/docs/` | **Swagger UI** — browse and call the API |
| `http://127.0.0.1:8000/api/redoc/` | ReDoc — the same schema, reference layout |
| `http://127.0.0.1:8000/api/schema/` | Raw OpenAPI 3 schema (YAML) |
| `http://127.0.0.1:8000/api/health/` | Health check — returns `{"status": "ok", "database": "ok"}` |
| `http://127.0.0.1:8000/admin/` | Django admin |
| `http://127.0.0.1:8000/api-auth/` | DRF session login, development only |

While `DEBUG` is on, visiting an API URL in a browser gives you the DRF
browsable API. Deployed builds render JSON only.

## API documentation

[drf-spectacular](https://drf-spectacular.readthedocs.io/) generates an
OpenAPI 3 schema from the code — serializers, viewsets and `@extend_schema`
annotations — so the docs can't drift from the implementation the way a
hand-written spec does.

**Swagger UI at `/api/docs/` is where you test endpoints.** Expand an
operation, hit *Try it out*, fill in the parameters and *Execute*. Writes need
a login, so sign in at `/api-auth/login/` first — Swagger shares the browser
session and sends the CSRF token for you.

The UI assets are served by `drf-spectacular-sidecar` out of this project
rather than a CDN, so the docs work offline and don't break if a third party
goes down. That does mean `collectstatic` has to run before deploying, or the
page loads unstyled.

### Documenting new endpoints

ViewSets built on serializers are picked up automatically. Function-based
views need a hint, since there's no serializer to inspect — `core/views.py`
shows the pattern:

```python
@extend_schema(
    tags=["system"],
    summary="Health check",
    responses={200: OpenApiResponse(response=HealthSerializer)},
)
@api_view(["GET"])
def health(request):
    ...
```

Check your work before committing — this fails on any warning, so an endpoint
the schema can't describe is caught here rather than showing up blank in the
UI:

```bash
python manage.py spectacular --validate --fail-on-warn --file schema.yaml
```

`core/tests.py` runs the same validation, so `manage.py test` catches it too.

### Access in production

Serving the full API surface publicly is a needless disclosure, so
`SERVE_PERMISSIONS` is `AllowAny` while `DEBUG` is on and `IsAdminUser` once
it's off — with `DEBUG=False`, all three doc URLs return 403 unless you're
signed in as staff. To publish them anyway, change `SERVE_PERMISSIONS` in
`SPECTACULAR_SETTINGS`.

## Layout

```
config/            Project configuration
  settings.py        All settings; environment-dependent values read from .env
  urls.py            Root URLconf — every API route is mounted under /api/
core/              Shared app: health check, and a home for cross-cutting code
  serializers.py     Response shapes, which also feed the OpenAPI schema
  views.py
  tests.py
manage.py
requirements.txt   Pinned, generated with `pip freeze`
.env.example       Template listing every variable the project reads
```

Domain apps (films, productions, press, …) go in the project root alongside
`core/` and register themselves in two places: `LOCAL_APPS` in
`config/settings.py`, and `api_urlpatterns` in `config/urls.py`.

```bash
python manage.py startapp films
```

## Configuration

Every environment-dependent value is read from `.env` via
[django-environ](https://django-environ.readthedocs.io/). `.env` is
git-ignored; `.env.example` is committed and documents each variable — **add
any new variable to it** so the next person knows it exists.

The ones you are most likely to touch:

| Variable | Notes |
|---|---|
| `DJANGO_SECRET_KEY` | Required, no default. Use a distinct value per environment. |
| `DJANGO_DEBUG` | `True` locally, never in production. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated; must list every hostname the API is served on. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins, scheme included, no trailing slash. |
| `DJANGO_SQLITE_PATH` | Path to the database file. |

### Talking to the frontend

The two apps are separate origins, so the frontend origin must be named in
`DJANGO_CORS_ALLOWED_ORIGINS`. It defaults to the Vite dev server
(`http://localhost:5173`), which is why the backend's `.env` and the
frontend's `VITE_PORT` have to agree.

In development you can skip CORS altogether: leave `VITE_API_BASE_URL` empty
on the frontend and its dev server proxies `/api` through to Django, so the
browser only ever sees one origin.

### Authentication and CSRF

`REST_FRAMEWORK` defaults to `SessionAuthentication` with
`IsAuthenticatedOrReadOnly` — reads are open, writes need a login. DRF enforces
CSRF on unsafe methods for session-authenticated requests, so the frontend has
to send a token back.

Django only issues the `csrftoken` cookie for views that ask for it, which is
why `core.views.health` carries `@ensure_csrf_cookie`: the React app calls it
on startup, and from then on has a token for its `POST`/`PATCH`/`DELETE`
requests. `core/tests.py` pins that behaviour — if you remove the decorator,
those tests fail rather than the frontend silently breaking.

This relies on the API being same-origin from the browser's point of view. For
a genuinely cross-site deployment, move to token authentication
(`rest_framework.authtoken`, or JWT via `djangorestframework-simplejwt`),
which sidesteps CSRF entirely.

## Database

SQLite is the production database here, not just a development convenience.
`config/settings.py` configures it accordingly:

- **WAL journal mode**, so readers don't block the writer;
- **`transaction_mode = "IMMEDIATE"`**, which takes the write lock up front
  and avoids mid-transaction "database is locked" failures;
- **a 20-second busy timeout**, so a concurrent writer waits instead of
  failing immediately.

This comfortably handles a content site's traffic. Two things to keep in mind
when deploying:

- Point `DJANGO_SQLITE_PATH` at persistent storage **outside** the deployment
  directory, or a redeploy will take the database with it.
- The database file is not in git, by design. Back it up on a schedule —
  `sqlite3 db.sqlite3 ".backup backup.sqlite3"` is safe to run against a live
  database, unlike copying the file.

## Commands

```bash
python manage.py runserver            # Development server
python manage.py test                 # Run the test suite
python manage.py makemigrations       # After changing models
python manage.py migrate              # Apply migrations
python manage.py check --deploy       # Production readiness check
python manage.py collectstatic        # Before deploying — includes Swagger UI assets

# Write the OpenAPI schema to a file, failing on anything it can't describe
python manage.py spectacular --validate --fail-on-warn --file schema.yaml
```

After installing or upgrading a package, re-pin the lockfile:

```bash
pip freeze > requirements.txt
```

## Deployment checklist

1. `DJANGO_DEBUG=False`, and a fresh `DJANGO_SECRET_KEY`.
2. Real hostnames in `DJANGO_ALLOWED_HOSTS`; the live frontend origin in
   `DJANGO_CORS_ALLOWED_ORIGINS`.
3. `DJANGO_SQLITE_PATH` on persistent storage, with backups configured.
4. `python manage.py migrate && python manage.py collectstatic --no-input`.
5. `python manage.py check --deploy` clean.
6. Serve through a WSGI server (`gunicorn config.wsgi` or `waitress-serve`)
   behind a reverse proxy; `runserver` is not for production.

With `DEBUG` off, the settings turn on HTTPS redirects, HSTS and secure
cookies — so terminate TLS at the proxy before you flip it.
