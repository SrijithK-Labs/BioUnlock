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

## Deploy to Vercel (recommended)

1. **Import the repo** at [vercel.com/new](https://vercel.com/new).
2. Set the project's **Root Directory** to `server`. Vercel detects the FastAPI
   app through `[tool.vercel] entrypoint = "app.main:app"` in `pyproject.toml`
   and installs dependencies with `uv` — no build command needed.
3. **Connect a database.** In the **Storage** tab, connect a Postgres database
   to this project. Vercel injects the connection string (often store-prefixed,
   e.g. `biounlockdb_DATABASE_URL`); the app detects it automatically, so you do
   **not** set a database URL by hand.
4. **Add the deployment secrets.** Add these **Environment Variables**:

   | Name | Value |
   | --- | --- |
   | `BIO_API_TOKEN` | a long random string (see below) |
   | `BIO_SIGNING_KEY` | stable Ed25519 private key PEM (generate once and retain) |

   `BIO_ENVIRONMENT` follows `VERCEL_ENV` on Vercel and defaults to production.
5. **Deploy.**
6. **Run the migrations once** against the new database (see
   [Migrations](#migrations)). SQLite would not persist on Vercel, so this step
   is what creates your schema in Postgres.

Generate the API token with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Enter the same token in the phone app (**Settings → API token**) and the Windows
agent (**Link this PC**). Without it, the server refuses every owner endpoint
in production — so a misconfigured deploy fails closed.
Generate the signing key once from `server/` with:

```bash
python -c "from app.core.security import ServerSigningKey; print(ServerSigningKey.generate().to_pem())"
```

## Run on a VM

Any small always-on host that runs Python 3.11+ works:

```bash
cd server
pip install -r requirements.txt
export BIO_ENVIRONMENT=production         # explicit fail-closed deployment mode
export BIO_API_TOKEN=<your-secret>          # shared owner API token
export BIO_SIGNING_KEY=<stable-ed25519-pem>  # keep stable and private
export BIO_DATABASE_URL=sqlite:///./biounlock.db   # optional; SQLite by default
alembic upgrade head                         # create the schema
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For local development, SQLite is sufficient. Put deployed instances behind
HTTPS (the WebAuthn relying party must be an HTTPS origin).

## Environment variables

`BIO_ENVIRONMENT` defaults to `production`; deployed environments require both
`BIO_API_TOKEN` and `BIO_SIGNING_KEY`. Only an explicitly configured automated
test harness may omit them. See [`../.env.example`](../.env.example) for the
local development settings.

| Variable | Required | Notes |
| --- | --- | --- |
| `BIO_API_TOKEN` | **yes** | Shared bearer secret for owner endpoints and enrollment |
| `BIO_SIGNING_KEY` | **yes** (deployed) | Stable Ed25519 private key from a secret store |
| `BIO_DATABASE_URL` | no | Overrides the auto-detected database URL |
| `BIO_RP_ID` | no | Defaults to `auto` (taken from the request host) |
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

Owner endpoints (passkey registration, device/passkey management, pairing
confirmation, activity history) and PC enrollment require `BIO_API_TOKEN`. The PC
agent authenticates with its own Ed25519 device credential after enrollment, and
only a paired, active device may open the agent WebSocket. See
[`../docs/security.md`](../docs/security.md) and
[`../docs/threat-model.md`](../docs/threat-model.md).
