# BioUnlock

<p align="center">
  <img src="logo/logo.png" alt="BioUnlock logo" width="140" />
</p>

> **Status: experimental.** BioUnlock works end to end: your phone authorizes a
> signed request over the Internet and the paired Windows PC verifies it and
> unlocks or locks itself via a native Credential Provider.

BioUnlock lets you unlock a paired Windows PC using your Android phone's
biometric authentication — even when the phone and the PC are on completely
different networks. The phone and PC communicate through a backend you host.

The PC never has to expose an inbound port, and Bluetooth/`same-Wi-Fi` is
never required.

## What works today

- FastAPI backend with WebAuthn passkeys, device pairing, and a signed
  authentication-request protocol. It is **single-owner**: there are no accounts
  or sessions by design.
- Flutter Android app with a configurable backend URL, passkey approval, PC
  pairing, and truthful request status.
- Windows **tray app** (PyInstaller `.exe` + installer) that links the PC, runs
  in the background, starts at login, connects outbound, independently verifies
  signed requests, and reports status back.
- Native Windows **Credential Provider** that signs you in at the logon screen
  from an approved request.
- MitM-friendly TLS posture, secure storage for device identity, revocation,
  security event history, and rate limiting.

## Repository layout

```
mobile/biounlock_mobile/   Flutter app (Android)
server/                    FastAPI backend + Alembic migrations + tests
pc-agent/                  Windows tray app + agent + credentials provider
docs/                      Architecture, protocol, threat model, security
.github/workflows/         CI
```

BioUnlock is meant to be **self-hosted per user**. Deploy `server/` somewhere
that runs Python (for example Vercel) and point both the phone app and the
Windows app at that URL. Because there are no accounts, treat the URL as a
secret — anyone who knows it can try to register a passkey or link a PC.

## Quick start (development)

### 1. Backend

```bash
cd server
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env          # edit values for local dev
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs: <http://localhost:8000/docs>

### 2. Mobile app

```bash
cd mobile/biounlock_mobile
flutter pub get
flutter run                       # on a connected Android device
```

In the app, open **Settings → Server**, enter your backend base URL
(e.g. `http://10.0.2.2:8000` from the Android emulator, or a reachable address),
and tap **Test Connection**.

Real passkeys require an HTTPS relying-party domain with a Digital Asset Links
association, so passkey login cannot be tested against bare `localhost` on a
physical device. See [`docs/mobile.md`](docs/mobile.md) for the passkey
requirement, build steps, and Android/Gradle troubleshooting (IPv6, Kotlin
incremental caches, corrupted Gradle caches).

### 3. PC agent

```bash
cd pc-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m biounlock_agent tray      # system tray app
# or run the background agent in the foreground:
python -m biounlock_agent run
```

## Environment / configuration

All backend configuration is read from environment variables or a `server/.env`
file. See `.env.example` for the full list with comments.

Both the mobile app and the Windows software let the user type in their own
backend URL. They never hardcode a server. HTTP is only allowed for development
hosts (localhost / private networks); production servers must be HTTPS.

## Tests

```bash
# Backend
cd server && pytest

# PC agent
cd pc-agent && pytest

# Flutter
cd mobile/biounlock_mobile && flutter analyze && flutter test
```

## Security

See `docs/security.md`, `docs/threat-model.md`, `docs/protocol.md`, and
`SECURITY.md`. Do not use this software where losing your primary Windows
credentials is not acceptable — it is experimental.

## License

MIT. See [LICENSE](LICENSE).