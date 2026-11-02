# BioUnlock backend

<p align="center">
  <img src="../logo/logo.png" alt="BioUnlock logo" width="110" />
</p>

FastAPI backend for BioUnlock. It is the WebAuthn relying party for phone
passkeys, pairs Windows PCs, and authorizes unlock/lock requests with a
short-lived, single-use, Ed25519-signed envelope that the PC verifies
independently. It is **single-owner**: no accounts, no sessions.

The whole point of this service is to be small and boring to host. Set the owner
API token and a stable server signing key as deployment secrets.

## Setup (Vercel, recommended)

Ten minutes, once. Nothing below has to be repeated later.

### 1. Import the repo and connect a database

1. **Import the repo** at [vercel.com/new](https://vercel.com/new).
2. Set the project's **Root Directory** to `server`. Vercel detects the FastAPI
   app through `[tool.vercel] entrypoint = "app.main:app"` in `pyproject.toml`
   and installs dependencies with `uv` — no build command needed.
3. **Connect a database.** In the **Storage** tab, connect a Postgres database
   (Neon works well) to this project. Vercel injects the connection string
   (often store-prefixed, e.g. `biounlockdb_DATABASE_URL`); the app detects it
   automatically, so you do **not** set a database URL by hand.

### 2. Generate the three secrets

Run these once, from a clone of this repository:

```bash
cd server
python -c "import secrets; print(secrets.token_urlsafe(32))"                      # API token
python -c "import secrets; print(secrets.token_urlsafe(32))"                      # enrollment token
python -c "from app.core.security import ServerSigningKey; print(ServerSigningKey.generate().to_pem())"
```

The last one prints an Ed25519 private key in PEM form. **Keep a copy of it.**
That key is the server's identity: every paired PC pins its public half, so
generating a new one means re-pairing every PC. If the Vercel project already
has a `BIO_SIGNING_KEY`, reuse that value instead of generating a new key.

### 3. Add the environment variables

Project → **Settings** → **Environment Variables**, for **Production**:

| Name | Value |
| --- | --- |
| `BIO_API_TOKEN` | the API token from step 2 |
| `BIO_ENROLLMENT_TOKEN` | the enrollment token from step 2 |
| `BIO_SIGNING_KEY` | the whole PEM block from step 2, real line breaks included |
| `BIO_RP_ID` | the domain Vercel serves, e.g. `biounlock.example.com` (no scheme or port) |

`BIO_ENVIRONMENT` follows `VERCEL_ENV` on Vercel and defaults to production.
Outside development, `BIO_RP_ID` must be pinned; leaving it at `auto` stops
startup. The server also refuses to start without `BIO_SIGNING_KEY`.

Enter the API token in the phone app (**Settings → API token**) and in the
Windows agent (**Link this PC**). Enter the enrollment token in the phone as
**Settings → Enrollment token**: the first passkey can be registered with the
API token alone, but every later add or remove also requires this value.

### 4. Deploy, then create the schema

Deploy from the **Deployments** tab. Git auto-deploys are switched off in this
repository (`server/vercel.json`), so pushing to GitHub does not deploy —
use **Redeploy** in the dashboard after changing environment variables.

Then run the migrations **once** against the database (see
[Migrations](#migrations)):

```powershell
cd server
$env:BIO_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Until this runs, **every request returns HTTP 500**: the app starts against an
empty database and has nowhere to keep the server configuration. The schema
lives in Postgres, so it survives every later deploy and never needs running
again unless a new migration is added.

### 5. Check that it is alive

```powershell
curl.exe https://<your-domain>/api/v1/health/live
```

A `200` means the backend is up. The Digital Asset Links document that Android
needs for passkeys is served at
`https://<your-domain>/.well-known/assetlinks.json`.

### What the server does on its own

- Reads the environment from `VERCEL_ENV`, so `/docs` stays off in production.
- Detects the Postgres URL from `DATABASE_URL` / `POSTGRES_URL` / any
  `*_DATABASE_URL` variable.
- Serves the Digital Asset Links document with the bundled release certificate
  fingerprint, so the shipped APK is associated with your domain.
- Derives the allowed WebAuthn origins from `BIO_RP_ID` and the asset links, so
  `BIO_ALLOWED_ORIGINS` is only needed for extra browser origins.

### If something is wrong

| Symptom | Cause |
| --- | --- |
| Every route returns HTTP 500 | `BIO_SIGNING_KEY` missing or malformed, or the schema was never created |
| `BIO_RP_ID must be pinned …` | `BIO_RP_ID` is unset or still `auto` outside development |
| `BIO_API_TOKEN is required` | `BIO_API_TOKEN` is unset |
| `BIO_ENROLLMENT_TOKEN is required` | A passkey exists and `BIO_ENROLLMENT_TOKEN` is unset |
| Passkey creation fails on the phone | The APK's signing certificate is not in the served asset links |

## Run on a VM

Any small always-on host that runs Python 3.11+ works:

```bash
cd server
pip install -r requirements.txt
export BIO_ENVIRONMENT=production         # explicit fail-closed deployment mode
export BIO_API_TOKEN=<your-secret>          # shared owner API token
export BIO_ENROLLMENT_TOKEN=<second-secret> # required to change passkeys
export BIO_RP_ID=biounlock.example.com       # pinned WebAuthn domain
export BIO_SIGNING_KEY=<stable-ed25519-pem>  # keep stable and private
export BIO_DATABASE_URL=sqlite:///./biounlock.db   # optional; SQLite by default
alembic upgrade head                         # create the schema
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For local development, SQLite is sufficient. Put deployed instances behind
HTTPS (the WebAuthn relying party must be an HTTPS origin).

## Environment variables

`BIO_ENVIRONMENT` defaults to `production`; deployed environments require
`BIO_API_TOKEN`, `BIO_SIGNING_KEY`, and a pinned `BIO_RP_ID`. Only an explicitly
configured automated test harness may omit them. See
[`../.env.example`](../.env.example) for the local development settings.

| Variable | Required | Notes |
| --- | --- | --- |
| `BIO_API_TOKEN` | **yes** | Shared bearer secret for owner endpoints and PC enrollment |
| `BIO_ENROLLMENT_TOKEN` | after the first passkey | Second secret required to add or remove passkeys |
| `BIO_SIGNING_KEY` | **yes** (deployed) | Stable Ed25519 private key from a secret store |
| `BIO_DATABASE_URL` | no | Overrides the auto-detected database URL |
| `BIO_RP_ID` | **yes** (deployed) | WebAuthn domain; `auto` (request host) is development-only |
| `BIO_ALLOWED_ORIGINS` | no | Extra origins; the request host and the Android app origin are added automatically |
| `BIO_ENVIRONMENT` | no | Auto-set from Vercel's `VERCEL_ENV`; keeps `/docs` off in production |

Rate limiting is always enabled outside the explicit test harness. Multi-worker
and serverless deployments should also use a shared edge/proxy limiter.

## Migrations

The app does **not** create tables at startup; run Alembic once per database:

```bash
cd server
# point at the production database
export BIO_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST/DBNAME"
# PowerShell instead: $env:BIO_DATABASE_URL = "postgresql+psycopg://..."
python -m alembic upgrade head
```

Re-run `alembic upgrade head` after any deploy that adds a migration.

## Run locally

```bash
cd server
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp ../.env.example .env           # then edit values
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive API docs: <http://localhost:8000/docs>.

## Tests

```bash
cd server
pip install -r requirements-dev.txt
pytest
ruff check .
```

## Security

Owner endpoints (device/passkey management, pairing confirmation, activity
history) and PC enrollment require `BIO_API_TOKEN`. Once a passkey exists,
adding or removing passkeys also requires `BIO_ENROLLMENT_TOKEN`, so a leaked
API token cannot enroll an attacker's authenticator. The PC agent authenticates
with its own Ed25519 device credential after enrollment, and only a paired,
active device may open the agent WebSocket. See
[`../docs/security.md`](../docs/security.md) and
[`../docs/threat-model.md`](../docs/threat-model.md).
