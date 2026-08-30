# Cypher Dashboard

A self-hosted Flask monitoring dashboard for HTTP, TCP, and ICMP services. It
runs each monitor on its own interval, stores append-only history in PostgreSQL,
tracks outage/recovery incidents, and displays live status, sample-based uptime,
response-time charts, and incident history behind Google login.

## Features

- HTTP checks with exact expected-status matching and redirects disabled
- TCP connection and ICMP ping checks with bounded timeouts
- One APScheduler interval job per service with overlap and duplicate protection
- Append-only checks and automatic up→down/down→up incident transitions
- Current up/down/unknown/stale state and 24h/7d/30d uptime
- Chart.js response-time history and incident table
- Validated HTML and JSON service CRUD
- Google OpenID Connect login, hardened sessions, and CSRF protection
- An explicit Google email allowlist required for production administrators
- PostgreSQL migrations plus an SQLite development/test fallback
- Automated runner, validation, CRUD, incident, summary, history, and auth tests

## Architecture

The dashboard uses a Flask application factory with blueprints for HTML, JSON
API, and authentication concerns, while SQLAlchemy persists monitor definitions,
append-only check results, and incident state. An embedded APScheduler instance
creates one interval job per service and dispatches HTTP, TCP, or ICMP runners;
ordinary network failures become result data so an unreachable target cannot
crash the scheduler. Each result is committed with an incident transition, and
the server-rendered dashboard reads aggregate availability while small JavaScript
requests refresh current state and Chart.js history. PostgreSQL indexes support
time-range queries, and Google OpenID Connect plus CSRF protection gates all
dashboard and management operations.

```text
Browser ── HTML/Jinja + authenticated JSON ──> Flask blueprints
                                                    │
                                              SQLAlchemy
                                                    │
                                                PostgreSQL
                                                    ▲
                                                    │ append result + transition incident
APScheduler ── one interval job per service ──> HTTP / TCP / ICMP runner
```

The scheduler is intentionally in-process to keep this home-lab project small.
Run one application worker; multiple workers would each create their own jobs.

## Technology

- Python 3.12+ and Flask
- PostgreSQL 17 with Psycopg 3
- Flask-SQLAlchemy / SQLAlchemy 2
- Flask-Migrate / Alembic
- APScheduler 3
- Authlib and Google OpenID Connect
- Jinja2, vanilla JavaScript, and Chart.js
- Flask-WTF / WTForms for validation and CSRF
- pytest, coverage, and Ruff

## Project structure

```text
app/
├── checks/                 # runners, persistence, scheduler
├── routes/                 # HTML and JSON blueprints
├── static/                 # CSS and small JavaScript modules
├── templates/              # server-rendered pages
├── auth.py                 # Google/local-development authentication
├── decorators.py           # login guard and safe redirects
├── extensions.py           # unbound Flask extensions
├── forms.py                # service form
├── models.py               # users, services, checks, incidents
├── services.py             # live summary/uptime queries
└── validation.py           # shared HTML/API target validation
migrations/                 # reviewed Alembic history
tests/                      # unit and integration tests
compose.yaml                # local PostgreSQL
compose.truenas.yaml        # TrueNAS SCALE Custom App template
Dockerfile                  # production application image
docker/entrypoint.sh        # migration and server startup
docs/truenas-scale.md       # TrueNAS deployment walkthrough
config.py                   # environment configuration
run.py                      # local/WSGI entry point
```

## Quick start with Docker PostgreSQL

Prerequisites:

- Python 3.12 or newer
- Docker Desktop or Docker Engine with Compose
- a Google account only if testing real Google login

From a fresh clone:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the generated value into `FLASK_SECRET_KEY` in `.env`. To explore the app
before configuring Google, set this development-only option:

```dotenv
ALLOW_INSECURE_DEV_AUTH=true
```

Then start PostgreSQL, migrate, and run Flask:

```bash
docker compose up -d db
docker compose ps
flask --app run.py db upgrade
python run.py
```

Open <http://127.0.0.1:5000>. Choose **Continue with local development account**
when that option is enabled. The application disables Flask's code reloader
while the scheduler is enabled, preventing duplicate background jobs; restart
`python run.py` after code changes.

Stop the application with `Ctrl+C`. Stop PostgreSQL without deleting its data:

```bash
docker compose stop
```

## Deploy on TrueNAS SCALE

TrueNAS SCALE 24.10 and newer can install the project as a Docker Compose Custom
App. The repository includes a non-root production image, a GHCR build workflow,
automatic migrations, a PostgreSQL health check, a persistent ZFS bind mount,
and a ready-to-customize `compose.truenas.yaml`.

Follow [the complete TrueNAS SCALE guide](docs/truenas-scale.md). Do not paste
the template into TrueNAS until every `CHANGE_ME` value and the `/mnt/POOL` path
has been replaced. The production Google callback must be an HTTPS hostname
routed through a reverse proxy to TrueNAS port 18000.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Primary SQLAlchemy URL; use `postgresql+psycopg://...` |
| `FLASK_SECRET_KEY` | Long random value used to sign sessions and CSRF tokens |
| `GOOGLE_OAUTH_CLIENT_ID` | Google Web application client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google Web application client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | Exact callback, normally `http://127.0.0.1:5000/auth/callback` |
| `FLASK_ENV` | `development` or `production` |
| `SCHEDULER_ENABLED` | Enables per-service background checks |
| `CHECK_TIMEOUT_SECONDS` | Global upper bound for a network check |
| `SESSION_COOKIE_SECURE` | Set `true` behind production HTTPS |
| `ALLOW_INSECURE_DEV_AUTH` | Local-only login bypass; production rejects `true` |
| `ALLOWED_GOOGLE_EMAILS` | Comma-separated trusted admin emails; required in production |

All secrets belong in `.env` or the deployment environment. `.env` is ignored by
Git. SQLite is used only when `DATABASE_URL` is absent; PostgreSQL is the primary
target.

## Configure Google login

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Configure Google Auth Platform Branding and Audience. For personal testing,
   use an External app and add your account as a test user. Also configure the
   application's email allowlist below; Google's basic identity scopes have a
   [testing-mode exception](https://support.google.com/cloud/answer/15549945).
4. Open **Google Auth Platform → Clients** and create an **OAuth client ID**.
5. Choose **Web application**.
6. Add this exact authorized redirect URI:

   ```text
   http://127.0.0.1:5000/auth/callback
   ```

7. Put the client ID and secret in `.env` and confirm the same callback is set in
   `GOOGLE_OAUTH_REDIRECT_URI`.
8. Set `ALLOW_INSECURE_DEV_AUTH=false`, restart Flask, and select **Continue with
   Google**.
9. Set `ALLOWED_GOOGLE_EMAILS=your-email@example.com` to restrict access to your
   account. Multiple trusted administrators can be separated by commas.

The redirect URI must match exactly—including scheme, host, port, path, case, and
trailing slash. Production must use an HTTPS callback on a domain you control.
The app requests only `openid email profile` and does not store Google access or
refresh tokens.

## Security model and limitations

This is a **shared, trusted-administrator home-lab dashboard**, not a multi-tenant
hosting service. Every allowed administrator can view, edit, and delete all
monitors. The creator field records attribution, not an ownership boundary.

Production startup requires a nonempty `ALLOWED_GOOGLE_EMAILS`. The Google
callback requires a verified email and rejects accounts outside the list.
Removing an account from the configured list also invalidates its session on
the next request after restart. An empty list in development permits any Google
account that completes login, so keep local development on loopback only.

Private network and loopback targets are intentionally supported. The target
validation is **not a complete SSRF defense**: it does not pin DNS resolutions or
prevent all aliases to metadata endpoints. Keep the application private, trust
every administrator, and use network firewall rules to restrict its reach.
Never give untrusted users access or treat this as an internet-facing service.

Check history currently grows without automatic retention. Plan backups and
storage monitoring for a long-running installation. The TrueNAS configuration
is a deployment template; an end-to-end TrueNAS deployment and container image
validation are still pending. No Docker image is published automatically when
this repository is pushed; its publishing workflow is manual and opt-in.

## Add a service

After signing in, select **Add service**:

- **HTTP:** enter a full `http://` or `https://` URL and expected status such as
  `200`.
- **TCP port:** enter `host:port`, such as `192.168.1.20:22`. Write IPv6 as
  `[2001:db8::1]:443`.
- **Ping:** enter a hostname or IP without a scheme or port.

Intervals range from 10 to 86,400 seconds. The first job runs immediately, and
the card updates through `/api/services` every 15 seconds. Private home-network
addresses are allowed intentionally; known cloud metadata targets, malformed
hosts, credentials in URLs, multicast addresses, and unspecified addresses are
rejected.

## Status and uptime semantics

- **Up:** the latest fresh check succeeded.
- **Down:** the latest fresh check failed.
- **Unknown:** no check has run yet.
- **Stale:** the latest check is older than the larger of twice the interval or
  the interval plus 30 seconds.
- **Uptime:** successful samples divided by all samples in the selected range.
  No samples display `N/A`, never an invented 100%.

HTTP success means the exact expected status code. Redirects are not followed.
Every check is appended, never overwritten. A first/down or up→down transition
opens one incident; the first later successful result resolves it and stores its
duration.

## JSON API

All endpoints except `/api/health` require a logged-in session.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Public application liveness |
| `GET` | `/api/services` | Live service summaries |
| `POST` | `/api/services` | Create a validated service |
| `PUT` | `/api/services/<id>` | Replace service configuration |
| `DELETE` | `/api/services/<id>` | Delete service and history |
| `GET` | `/api/services/<id>/history?range=24h\|7d\|30d` | Up to 2,000 chronological check points |
| `GET` | `/api/services/<id>/incidents` | Up to 100 newest incidents |

Mutating API calls require the CSRF token rendered in the page's `csrf-token`
meta tag, sent as `X-CSRFToken`. Successful responses use `data` and `error`
fields; validation failures contain field-specific errors.

## Database migrations

The initial migration creates named constraints and indexes for time-range and
incident queries. Apply committed migrations after every pull:

```bash
flask --app run.py db upgrade
```

When changing models:

```bash
flask --app run.py db migrate -m "describe the schema change"
flask --app run.py db check
flask --app run.py db upgrade
```

Always inspect generated revisions. Alembic cannot infer every rename or
dialect-specific object. The initial downgrade explicitly removes PostgreSQL's
native `check_type` enum so upgrade/downgrade cycles remain repeatable.

## Tests and code quality

```bash
ruff check .
pytest -q
pytest --cov=app --cov-report=term-missing
flask --app run.py db check
```

The fast suite runs against SQLite and covers shared validation, CRUD, runners,
all incident transitions, scheduler dispatch, uptime/status summaries, history,
CSRF, login guards, safe redirects, and mocked Google callback behavior. Migration
and scheduler smoke tests should also be run against PostgreSQL because its enum,
timezone, partial-index, and transaction behavior differ from SQLite.

## Production notes

Do not use Flask's development server publicly. One production example is:

```bash
gunicorn --workers 1 --threads 4 --bind 0.0.0.0:8000 run:app
```

The single worker is deliberate while APScheduler is embedded. Put a TLS reverse
proxy such as Caddy or Nginx in front, set `FLASK_ENV=production`, configure a
production PostgreSQL URL and strong secret, set `SESSION_COOKIE_SECURE=true`,
disable development authentication, and register the exact HTTPS Google
callback. Run migrations as a release step. Scaling the web tier beyond one
worker requires moving the scheduler into one dedicated process.

## Troubleshooting

**`redirect_uri_mismatch` from Google**

The callback generated by the app and the Google Console entry differ. Match
`http://127.0.0.1:5000/auth/callback` exactly for local development.

**Ping checks always fail**

ICMP sockets may require an OS/container capability. Do not run the complete web
app as root. Grant only the required ping capability or use HTTP/TCP checks.

**Duplicate checks**

More than one application process or the development reloader started a
scheduler. Use `python run.py` as supplied or one Gunicorn worker.

**`Working outside of application context`**

A scheduler job accessed Flask extensions without `app.app_context()`. The
included scheduler wrapper already pushes it; preserve that boundary.

**Database connection refused**

Run `docker compose ps` and `docker compose logs db`. Confirm port 5432 is free
and `DATABASE_URL` uses `postgresql+psycopg://`.

**Chart does not appear**

The browser needs access to the pinned Chart.js CDN. The JSON history endpoint
and incident table remain available even if the CDN is blocked.

## Interview summary

This project demonstrates a small but complete monitoring pipeline: scheduled
network I/O is isolated from persistence, failures are modeled as data, state
transitions are transactional, and indexed history powers both aggregate and
time-series views. The important operational tradeoff is the embedded scheduler:
it minimizes infrastructure for a home lab but constrains deployment to one
worker until scheduling is split into a dedicated process.
