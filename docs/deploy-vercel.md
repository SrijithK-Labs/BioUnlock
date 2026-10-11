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

## Environment variables to set in Vercel

| Variable | Example | Notes |
| --- | --- | --- |
| `BIO_ENVIRONMENT` | `production` | |
| `BIO_SECRET_KEY` | *(long random string)* | not a root of trust, but must not be the default |
| `BIO_DATABASE_URL` | `postgresql+psycopg://user:pw@host/db` | optional — auto-detected from the Postgres integration (see caveat 1) |
| `BIO_RP_ID` | `your-app.vercel.app` | effective domain, no scheme/port |
| `BIO_ALLOWED_ORIGINS` | `https://your-app.vercel.app,android:apk-key-hash:5DVyir7YN4Fg8vd14Av1I_5Ao1FkP4pMZXdn0638qAI` | WebAuthn origins |
| `BIO_CORS_ORIGINS` | `https://your-app.vercel.app` | |
| `BIO_SIGNING_KEY` | *(PEM contents)* | **required** — see caveat 2 |
| `BIO_COOKIE_SECURE` | `true` | behind HTTPS |
| `BIO_RATE_LIMIT_ENABLED` | `true` | |

## Caveats

1. **SQLite does not persist on Vercel.** The filesystem is ephemeral, so the
   default `sqlite:///./biounlock.db` loses every device and pairing on each
   deploy. In the project's **Storage** tab create a **Postgres** database
   (Marketplace → Neon) and connect it; Vercel injects `DATABASE_URL` /
   `POSTGRES_URL`, which the app now adopts automatically (and rewrites to the
   `psycopg` driver). If you prefer, set `BIO_DATABASE_URL` yourself instead.
   Then run migrations once against that database from your machine:

   ```powershell
   cd server
   $env:BIO_DATABASE_URL = "postgresql+psycopg://..."
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

2. **The server signing key must stay stable.** PC agents pin this Ed25519 key
   at pairing; if it changes they refuse envelopes. The default file location is
   ephemeral on Vercel, so provide the key as the `BIO_SIGNING_KEY` env var.
   Generate a key and copy the PEM into the Vercel variable (literal `\n` is
   accepted for a single-line value):

   ```powershell
   cd server
   .\.venv\Scripts\python.exe -c "from pathlib import Path; from app.core.security import ServerSigningKey; k=ServerSigningKey(Path('signing.pem'), overwrite=True); print(k.path.read_text())"
   ```

   Keep the same value across deploys; never commit it.

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
