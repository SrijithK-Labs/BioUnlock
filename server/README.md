# BioUnlock backend

<p align="center">
  <img src="../logo/logo.png" alt="BioUnlock logo" width="110" />
</p>

FastAPI backend for BioUnlock. It is the WebAuthn relying party for phone
passkeys, pairs Windows PCs, and authorizes unlock/lock requests with a
short-lived, single-use, Ed25519-signed envelope that the PC verifies
independently. It is **single-owner**: no accounts, no sessions.

The whole point of this service is to be small and boring to host. **The only
secret you have to set is `BIO_API_TOKEN`.**

## Deploy to Vercel (recommended)

1. **Import the repo** at [vercel.com/new](https://vercel.com/new).
2. Set the project's **Root Directory** to `server`. Vercel detects the FastAPI
   app through `[tool.vercel] entrypoint = "app.main:app"` in `pyproject.toml`
   and installs dependencies with `uv` — no build command needed.
3. **Connect a database.** In the **Storage** tab, connect a Postgres database
   to this project. Vercel injects the connection string (often store-prefixed,
   e.g. `biounlockdb_DATABASE_URL`); the app detects it automatically, so you do
   **not** set a database URL by hand.
4. **Add the API key.** Add one **Environment Variable**:

   | Name | Value |
   | --- | --- |
   | `BIO_API_TOKEN` | a long random string (see below) |

   That is the only required variable. Optionally also set
   `BIO_SECRET_KEY` and `BIO_ENVIRONMENT=production` (the latter is usually
   inferred from `VERCEL_ENV`).
5. **Deploy.**
6. **Run the migrations once** against the new database (see
   [Migrations](#migrations)). SQLite would not persist on Vercel, so this step
   is what creates your schema in Postgres.

Generate a token with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Enter the same token in the phone app (**Settings → API token**) and the Windows
agent (**Link this PC**). Without it, the server refuses every owner endpoint in
production — so a misconfigured deploy fails closed.

## Run on a VM

Any small always-on host that runs Python 3.11+ works:

```bash
cd server
pip install -r requirements.txt
export BIO_API_TOKEN=<your-secret>          # set only this secret
export BIO_DATABASE_URL=sqlite:///./biounlock.db   # optional; SQLite by default
alembic upgrade head                         # create the schema
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

With SQLite and a file-based signing key this needs no other configuration. Put
it behind HTTPS (the WebAuthn relying party must be an HTTPS origin).

## Environment variables

Only `BIO_API_TOKEN` is required in production. Everything else has a safe
default. See [`../.env.example`](../.env.example) for the full annotated list.

| Variable | Required | Notes |
| --- | --- | --- |
| `BIO_API_TOKEN` | **yes** (production) | Shared bearer secret for owner endpoints and enrollment |
| `BIO_DATABASE_URL` | no | Overrides the auto-detected database URL |
| `BIO_SIGNING_KEY` | no | The Ed25519 key is generated and stored in the DB on first use |
| `BIO_RP_ID` | no | Defaults to `auto` (taken from the request host) |
| `BIO_ALLOWED_ORIGINS` | no | Extra origins; the request host and the Android app origin are added automatically |
| `BIO_ENVIRONMENT` | no | Auto-set from Vercel's `VERCEL_ENV`; keeps `/docs` off in production |
| `BIO_SECRET_KEY` | recommended | Not a root of trust, but must not be the default |
| `BIO_RATE_LIMIT_ENABLED` | no | In-process rate limiting (default on) |

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

Owner endpoints (passkey registration, device/passkey management, pairing
confirmation, activity history) and PC enrollment require `BIO_API_TOKEN`. The PC
agent authenticates with its own Ed25519 device credential after enrollment, and
only a paired, active device may open the agent WebSocket. See
[`../docs/security.md`](../docs/security.md) and
[`../docs/threat-model.md`](../docs/threat-model.md).
