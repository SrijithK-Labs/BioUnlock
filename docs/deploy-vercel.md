# Deploying the BioUnlock backend to Vercel

The backend lives in `server/` and is a FastAPI app. Vercel has a native
**FastAPI preset**: it detects the ASGI `app` and serves it on every route, so
no `api/` function or catch-all rewrite is needed. The entrypoint is declared in
`server/pyproject.toml`:

```toml
[tool.vercel]
entrypoint = "app.main:app"
```

## Project setup

1. **Root Directory = `server`.** In the Vercel project settings set the root
   directory to `server`, otherwise Vercel will not find the app or
   dependencies.
2. Dependencies are declared in `server/pyproject.toml` (`[project].dependencies`).
   Vercel installs them with `uv`. (`server/requirements.txt` is kept in sync for
   local `pip` installs.) The `app` package is importable because the project
   root is `server/`.
3. Vercel pins a Python version; add a `server/.python-version` (e.g. `3.12`) if
   you want it fixed.

## Keep secrets out of GitHub

- **Never commit a real `.env`.** It is already ignored by the root and
  `server/.gitignore`; only `.env.example` (placeholders) is tracked.
- Set real values as **Environment Variables** in the Vercel dashboard (or with
  `vercel env add`). They live on Vercel, not in the repo. `.vercel/` is ignored.
- If a secret ever *was* committed, rotate it — deleting the file is not enough.

Check before you push:

```powershell
git status --short          # no .env should ever appear
git ls-files | Select-String -Pattern '\.env$|\.pem$|\.key$|signing'
```

## Environment variables

Connect Postgres and configure both required secrets:

| Variable | Required? | Notes |
| --- | --- | --- |
| *(Postgres integration)* | **yes** | In the **Storage** tab, connect a Postgres database; the connection string is auto-detected (see caveat 1) |
| `BIO_DATABASE_URL` | optional | Override the auto-detected database URL |
| `BIO_SIGNING_KEY` | **yes** | Stable Ed25519 private key from a deployment secret store; generate once and retain it across deploys |
| `BIO_RP_ID` | optional | Defaults to `auto`: derived from the request host |
| `BIO_ALLOWED_ORIGINS` | optional | Extra origins; the current host and the Android app origin are added automatically |
| `BIO_ENVIRONMENT` | optional | Defaults to production; on Vercel it follows `VERCEL_ENV` unless explicitly set |
| `BIO_API_TOKEN` | **yes** | Shared bearer secret for owner endpoints and enrollment; without it those endpoints fail closed |
| `BIO_CORS_ORIGINS` | optional | Browser tooling only |

## Caveats

1. **SQLite does not persist on Vercel.** The filesystem is ephemeral, so the
   default `sqlite:///./biounlock.db` loses every device and pairing on each
   deploy. In the project's **Storage** tab, connect a **Postgres** database;
   Vercel injects `DATABASE_URL` / `POSTGRES_URL` (often store-prefixed, e.g.
   `biounlockdb_DATABASE_URL`), which the app adopts automatically (and rewrites
   to the `psycopg` driver, preferring the pooled URL). If you prefer, set
   `BIO_DATABASE_URL` yourself instead.
   Then run migrations once against that database from your machine:

   ```powershell
   cd server
   $env:BIO_DATABASE_URL = "postgresql+psycopg://..."
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

   (If the direct/unpooled host will not resolve, use the pooled host — it works
   for DDL too.)

2. **The server signing key must stay stable.** Generate an Ed25519 private key
   once with `python -c "from app.core.security import ServerSigningKey; print(ServerSigningKey.generate().to_pem())"`
   and store it as `BIO_SIGNING_KEY` in Vercel's encrypted environment variables.
   Never regenerate it during deploys: paired PCs pin its public identity and
   would require re-pairing if it changes.

3. **WebSockets.** The agent's primary channel is a WebSocket with an automatic
   REST `inbox` fallback, so delivery keeps working even if the platform does
   not keep the socket open.

## Alternative: a small always-on VM

If cold starts, WebSockets, or the managed-database requirement are a poor fit,
run the backend on any small always-on host instead:

```powershell
cd server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

with a local `server/.env` (SQLite and a development database key are fine for
local testing). Deployed instances must use a stable `BIO_SIGNING_KEY` secret.
