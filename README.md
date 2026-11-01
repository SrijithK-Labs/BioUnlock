# BioUnlock

<p align="center">
  <img src="logo/logo.png" alt="BioUnlock logo" width="140" />
</p>

**Unlock your Windows PC with your phone's fingerprint — from anywhere.**

BioUnlock pairs an Android phone with a Windows PC through a small backend you
host yourself. Approve an unlock with the phone's biometrics and the phone sends
a signed request over the Internet; the PC independently verifies it and signs
you in through a native Windows Credential Provider. The PC never opens an
inbound port, and Bluetooth or "same Wi-Fi" is never required.

> **Status: experimental.** It works end to end today and is meant for your own
> machine — your Windows password stays a working sign-in option throughout. It
> has not been independently audited yet, so avoid making it the only credential
> on a device you could not recover. [`SECURITY.md`](SECURITY.md) lists exactly
> where each secret is stored.

## Download

Prebuilt artifacts are attached to
[**Releases**](https://github.com/SrijithK-Labs/BioUnlock/releases):

| Platform | Files | What it is |
| --- | --- | --- |
| Windows | `BioUnlock-0.1.0-windows-x64.exe` | Self-installing tray app that links and controls the PC |
| Android | `BioUnlock-1.0.0-android.apk` | Phone authenticator (passkey) |

**Windows app:** download `BioUnlock-0.1.0-windows-x64.exe` and double-click it.
It installs itself — one file, no separate script — through a small setup
wizard. From a terminal, run:

```powershell
.\BioUnlock-0.1.0-windows-x64.exe install
```

The wizard lets you choose sign-in unlock, start-at-login, the Start Menu
shortcut, and the post-install launch, then shows each step as it runs. It
copies the app to `%LOCALAPPDATA%\BioUnlock` and launches the tray icon. No
admin rights are needed for that. If sign-in unlock stays enabled, it then asks
once for elevation (**one UAC prompt**) to register the bundled Windows
Credential Provider and a SYSTEM startup task, which together power
logon-screen unlock — including after a restart; declining shows a Retry button
and just skips that step. That same prompt moves the agent's profile to
`%ProgramData%\BioUnlock` and migrates an existing link automatically. For
scripted installs run
`.\BioUnlock-0.1.0-windows-x64.exe install --silent`. If Windows **Smart App
Control** blocks the unsigned `.exe`, install from source with
`powershell -ExecutionPolicy Bypass -File pc-agent\install-agent.ps1 -FromSource`
(it launches via `pythonw.exe`, which Smart App Control allows).

**Phone app:** download `BioUnlock-1.0.0-android.apk` and open it on your phone
to install (allow "install unknown apps" when prompted).

You still need to **host the backend** yourself (one-time, a few minutes) — see
[Quick start](#quick-start). The Windows app needs your backend **URL** and **API
token**; the phone uses the same two, plus the **enrollment token** once a
passkey exists.

## How it works

```
  Phone (passkey)            Your backend                 Windows PC
  ───────────────  request   ─────────────    envelope   ──────────────
  biometric  ─────────────▶  verify + sign  ───────────▶ agent verifies
  approval                   & store                    signature + replay
                                                            │
                                                            ▼
                                              Credential Provider signs in
```

The phone's passkey private key never leaves the phone, and every action is
authorized by a short-lived, single-use, Ed25519-signed envelope that the PC
checks before doing anything. See [`docs/architecture.md`](docs/architecture.md),
[`docs/protocol.md`](docs/protocol.md), and
[`docs/threat-model.md`](docs/threat-model.md).

## Repository layout

```
mobile/biounlock_mobile/   Flutter Android app
server/                    FastAPI backend + Alembic migrations + tests
pc-agent/                  Windows tray app + agent + credential provider
docs/                      Architecture, protocol, threat model, security
```

BioUnlock is **self-hosted and single-owner** by design: there are no accounts or
sessions. Treat your backend URL as private — anyone who knows it *and* your API
token could try to enroll a device.

## Quick start

### 1. Host the backend

One-time setup, about ten minutes. In order:

1. **Deploy the server.** Import this repo at [vercel.com/new](https://vercel.com/new),
   set the project's **Root Directory** to `server`, and connect a Postgres
   database in the **Storage** tab. The connection string is detected
   automatically.
2. **Generate three values**, from a clone of this repository:

   ```bash
   cd server
   python -c "import secrets; print(secrets.token_urlsafe(32))"   # API token
   python -c "import secrets; print(secrets.token_urlsafe(32))"   # enrollment token
   python -c "from app.core.security import ServerSigningKey; print(ServerSigningKey.generate().to_pem())"
   ```

   The last one prints an Ed25519 private key. Keep a copy: it is the server's
   identity, and every paired PC pins its public half.

3. **Add them as environment variables**: `BIO_API_TOKEN`, `BIO_ENROLLMENT_TOKEN`,
   `BIO_SIGNING_KEY` (the whole PEM block, line breaks included) and `BIO_RP_ID`
   = the domain you serve from, without scheme or port. Outside development the
   server refuses to start without the signing key and a pinned RP ID.
4. **Deploy, then create the schema.** Run the migrations once against the
   database:

   ```powershell
   cd server
   $env:BIO_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME"
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

   The app does not create tables itself, so **every route returns HTTP 500
   until this has run**. The schema lives in Postgres and survives later
   deploys.
5. **Check** that `https://<your-domain>/api/v1/health/live` returns `200`.

Everything else is automatic: the environment follows `VERCEL_ENV`, the database
URL is detected, the Digital Asset Links document is served with the bundled
release certificate, and the allowed WebAuthn origins follow `BIO_RP_ID`.

Full steps, the "what is automatic" list, and a troubleshooting table:
[`server/README.md`](server/README.md).

**Any small VM:** see [`server/README.md`](server/README.md#run-on-a-vm).

### 2. Phone app

Install `BioUnlock-1.0.0-android.apk` from [Releases](https://github.com/SrijithK-Labs/BioUnlock/releases)
(or build it — see [`mobile/biounlock_mobile/README.md`](mobile/biounlock_mobile/README.md)).
In the app open **Settings → Server**, enter your backend URL, then enter the same
**API token**. The first passkey can be added with that token alone; afterwards
also enter the **enrollment token** under Settings so the app may add or remove
passkeys.

Real passkeys need an HTTPS domain with a Digital Asset Links association (your
backend URL). See [`docs/mobile.md`](docs/mobile.md) for the passkey requirement
and build troubleshooting.

### 3. Windows app

Install `BioUnlock-0.1.0-windows-x64.exe` — it is self-installing (per-user, no admin needed) and
bundles the Credential Provider plus a SYSTEM startup task, both registered after
one UAC prompt so logon-screen unlock keeps working after a restart. Then in
the tray app enter the backend **URL** and **API key** and click **Link this PC**,
scanning the QR code with the phone. The API key is needed because linking
enrolls the PC through the backend's `POST /api/v1/devices/enroll` endpoint, which your
backend protects with `BIO_API_TOKEN` — so a stranger who only knows the URL
still cannot add a device. It is entered once and stored on the PC; afterwards
the agent authenticates with its own signed device key. To unlock the actual
logon screen, store your Windows password in the tray. Full steps:
[`pc-agent/README.md`](pc-agent/README.md).

## Configuration: two tokens

`BIO_API_TOKEN` is shared by all three components:

1. **Server** — as a Vercel environment variable (or `server/.env` locally).
2. **Phone** — Settings → API token.
3. **PC agent** — the Link dialog (or `--token` / `BIOUNLOCK_AGENT_TOKEN`).

The phone sends it as `Authorization: Bearer <token>` on every owner call, and
the PC agent sends it once when enrolling, then authenticates with its own signed
device key. In production the server refuses owner endpoints if the token is
unset (fail closed).

`BIO_ENROLLMENT_TOKEN` is a second secret shared by the server and the phone
(Settings → Enrollment token). The first passkey bootstraps with the API token
alone; after that, adding or removing a passkey also requires this token as
`X-BioUnlock-Enrollment`, so a leaked API token cannot enroll an attacker's
passkey. A deployment that already has a passkey fails closed when this token is
unset.

Pinned `BIO_RP_ID` is the WebAuthn domain (no scheme or port). Changing it later
invalidates every registered passkey. Packaged mobile and Windows apps require
HTTPS. Mobile debug builds allow private-LAN HTTP; PC source runs require the
explicit `BIOUNLOCK_ALLOW_INSECURE_HTTP=1` development opt-in.

## Build from source

```bash
# Backend
cd server && pip install -r requirements.txt && uvicorn app.main:app --reload

# Phone
cd mobile/biounlock_mobile && flutter pub get && flutter run

# Windows agent
cd pc-agent && pip install -r requirements.txt && python -m biounlock_agent tray
```

## Tests

```bash
cd server && pytest && ruff check .          # backend
cd pc-agent && pytest && ruff check .         # Windows agent
cd mobile/biounlock_mobile && flutter analyze && flutter test   # phone
```

## Security

See [`SECURITY.md`](SECURITY.md), [`docs/security.md`](docs/security.md),
[`docs/threat-model.md`](docs/threat-model.md), and
[`docs/protocol.md`](docs/protocol.md).

## License

MIT. See [LICENSE](LICENSE).
