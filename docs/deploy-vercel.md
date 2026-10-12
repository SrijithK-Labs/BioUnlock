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

Only the **Postgres integration** is actually required. Connect it and the app
does the rest — no other env vars are needed:

| Variable | Required? | Notes |
| --- | --- | --- |
| *(Postgres integration)* | **yes** | Storage → Marketplace → **Postgres (Neon)**; the connection string is auto-detected (see caveat 1) |
| `BIO_DATABASE_URL` | optional | Override the auto-detected database URL |
| `BIO_SIGNING_KEY` | optional | The server key is generated and stored in the database by default (see caveat 2) |
| `BIO_RP_ID` | optional | Defaults to `auto`: derived from the request host |
| `BIO_ALLOWED_ORIGINS` | optional | Extra origins; the current host and the Android app origin are added automatically |
| `BIO_ENVIRONMENT` | optional | Auto-set from Vercel's `VERCEL_ENV` (keeps `/docs` private in production) |
| `BIO_SECRET_KEY` | recommended | Not a root of trust, but must not be the default |
| `BIO_API_TOKEN` | recommended | Shared bearer secret the mobile app sends on all owner endpoints; **required** in production (owner endpoints refuse to serve without it) |
| `BIO_CORS_ORIGINS` | optional | Browser tooling only |
| `BIO_COOKIE_SECURE` | optional | `true` behind HTTPS |

## Caveats

1. **SQLite does not persist on Vercel.** The filesystem is ephemeral, so the
   default `sqlite:///./biounlock.db` loses every device and pairing on each
   deploy. In the project's **Storage** tab create a **Postgres** database
   (Marketplace → Neon) and connect it; Vercel injects `DATABASE_URL` /
   `POSTGRES_URL` (often store-prefixed, e.g. `biounlockdb_DATABASE_URL`), which
   the app adopts automatically (and rewrites to the `psycopg` driver, preferring
   the pooled URL). If you prefer, set `BIO_DATABASE_URL` yourself instead.
   Then run migrations once against that database from your machine:

   ```powershell
   cd server
   $env:BIO_DATABASE_URL = "postgresql+psycopg://..."
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

   (If the direct/unpooled host will not resolve, use the pooled host — it works
   for DDL too.)

2. **The server signing key stays stable with no setup.** PC agents pin this
   Ed25519 key at pairing, so it must not change across restarts/deploys. The app
   generates a key on first use and stores it in the `server_config` row, so it
   survives cold starts automatically. To inject your own instead (e.g. from a
   secret manager), set `BIO_SIGNING_KEY` to the PEM (literal `\n` accepted).

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

with a local `server/.env` (SQLite and a file-based signing key are fine there).
