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

> **Status: experimental.** It works end to end today. Don't use it where losing
> your primary Windows credentials would be unacceptable.

## Download

Prebuilt artifacts are attached to
[**Releases**](https://github.com/SrijithK-Labs/BioUnlock/releases):

| Platform | File | What it is |
| --- | --- | --- |
| Windows | `BioUnlock.exe` + `install-agent.ps1` | Tray app that links and controls the PC |
| Android | `app-release.apk` | Phone authenticator (passkey) |

You still need to **host the backend** yourself (one-time, a few minutes) — see
[Quick start](#quick-start). The Windows installer and the phone app both need
only two things: your backend **URL** and your **API token**.

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

The only secret you must set is your **API token**. Everything else — the
database, the signing key, and the WebAuthn relying-party domain — is detected
automatically.

**Vercel (recommended, serverless):** import this repo, set the project's **Root
Directory** to `server`, **connect a database** (Storage tab), and add one
environment variable for the API key:

```
BIO_API_TOKEN = <your-secret>
```

Then run the migrations once against that database. Full steps:
[`server/README.md`](server/README.md).

**Any small VM:** see [`server/README.md`](server/README.md#run-on-a-vm).

Generate a token with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Phone app

Install `app-release.apk` from [Releases](https://github.com/SrijithK-Labs/BioUnlock/releases)
(or build it — see [`mobile/biounlock_mobile/README.md`](mobile/biounlock_mobile/README.md)).
In the app open **Settings → Server**, enter your backend URL, then enter the same
**API token**.

Real passkeys need an HTTPS domain with a Digital Asset Links association (your
backend URL). See [`docs/mobile.md`](docs/mobile.md) for the passkey requirement
and build troubleshooting.

### 3. Windows app

Install `BioUnlock.exe` via the per-user installer (no admin needed), then in the
tray app enter the backend **URL** and **API token** and click **Link this PC**,
scanning the QR code with the phone. To unlock the actual logon screen, also
install the Credential Provider and store your Windows credential. Full steps:
[`pc-agent/README.md`](pc-agent/README.md).

## Configuration: just the token

Set `BIO_API_TOKEN` in three places — that is the only shared secret:

1. **Server** — as a Vercel environment variable (or `server/.env` locally).
2. **Phone** — Settings → API token.
3. **PC agent** — the Link dialog (or `--token` / `BIOUNLOCK_AGENT_TOKEN`).

The phone sends it as `Authorization: Bearer <token>` on every owner call, and
the PC agent sends it once when enrolling, then authenticates with its own signed
device key. In production the server refuses owner endpoints if the token is
unset (fail closed). HTTP is allowed only for development hosts; production must
be HTTPS.

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
