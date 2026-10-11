# BioUnlock

> **Status: experimental.** BioUnlock is under active development. Remote
> authentication across networks works; actual Windows login-screen unlocking
> is NOT implemented yet and is a separate future milestone.

BioUnlock lets you unlock a paired Windows PC using your Android phone's
biometric authentication — even when the phone and the PC are on completely
different networks. The phone and PC communicate through a backend you host.

The PC never has to expose an inbound port, and Bluetooth/`same-Wi-Fi` is
never required.

## What works today (initial MVP)

- FastAPI backend with accounts, WebAuthn passkeys, sessions, and a signed
  authentication-request protocol.
- Flutter Android app with configurable backend URL, passkey enrollment,
  PC pairing, and truthful request status.
- Windows **Python agent** (runs as a Windows Service or console app) that
  registers the PC, connects outbound, independently verifies signed requests,
  and reports status back.
- PySide6 setup GUI for the Windows software.
- MitM-friendly TLS posture, secure storage for device identity, revocation,
  security event history, and rate limiting.

### What is NOT included yet

- **Unlocking the actual Windows logon screen.** The MVP delivers a truthful
  "request verified" result. The supported native Windows Credential Provider
  integration is a separate, explicitly out-of-scope milestone documented in
  `docs/windows-authentication.md`.

## Repository layout

```
mobile/biounlock_mobile/   Flutter app (Android)
server/                    FastAPI backend + Alembic migrations + tests
pc-agent/                  Windows PC agent, background service, PySide6 GUI
pc-agent/installer/        PyInstaller + Inno Setup packaging
windows-auth/              Native Windows logon integration (future milestone)
installer/                 Combined installer notes
docs/                      Architecture, protocol, threat model, security
.github/workflows/         CI
```

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
python -m biounlock_agent.gui       # setup GUI
# or run the background agent in the foreground:
python -m biounlock_agent
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