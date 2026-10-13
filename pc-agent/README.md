# BioUnlock Windows app

<p align="center">
  <img src="../logo/logo.png" alt="BioUnlock logo" width="110" />
</p>

Outbound-only Windows agent. It pairs a PC with your BioUnlock backend, pins the
server's Ed25519 signing key, independently verifies every signed authorization
envelope, and reports a truthful result. It never opens an inbound port and never
transmits a Windows password.

The user-facing app is a **system tray icon** that lets you enter your backend
URL and API key, link this PC by scanning a QR code with the phone, and
start/stop the background agent. It starts automatically at login.

## What it does

- `remote_unlock` mints a short-lived, single-use ticket that the native Windows
  Credential Provider reads to sign you in at the logon screen.
- `remote_lock` locks the workstation (reported as `already_locked` when it
  already is).
- The agent reports whether the PC is currently locked/unlocked.

## Install (end users)

Download the prebuilt `BioUnlock.exe` from
[**Releases**](https://github.com/SrijithK-Labs/BioUnlock/releases) — you do not
need Python or any build tools. **The one `.exe` installs everything.**

1. Double-click `BioUnlock.exe` (or run `BioUnlock.exe install` from a
   terminal). Because it is not installed yet, it sets itself up: it copies
   itself to `%LOCALAPPDATA%\BioUnlock`, adds itself to Start-up, and creates a
   Start Menu shortcut. No admin rights are needed for this part.
2. It then asks once for elevation (**one UAC prompt**) to register the bundled
   Windows Credential Provider — the component that unlocks the real logon
   screen. Declining only skips logon-screen unlock; everything else still
   installs.
3. Click the tray icon, enter your backend URL and the **API key**, then
   **Link this PC** and scan the QR code with the phone app.

   The API key **is required** here. Linking enrolls this PC through the
   backend's `POST /devices/enroll` endpoint, which is protected by your
   backend's `BIO_API_TOKEN`, so someone who only knows your URL still cannot
   register a device. You only enter it once: the agent stores it
   (DPAPI-protected) and reuses it for future re-links. After pairing, the PC
   authenticates with its own signed device key, so the token is not sent again.
4. To unlock the actual Windows logon screen, store your Windows password with
   **Set Windows password…** in the tray menu (or
   `python -m biounlock_agent set-credential`).

If Windows **Smart App Control** blocks the unsigned `.exe`, install the source
launcher instead (it runs with `pythonw.exe`, which Smart App Control allows):

```powershell
powershell -ExecutionPolicy Bypass -File install-agent.ps1 -FromSource
```

`install-agent.ps1` remains available for scripted installs; for a packaged
`.exe` it simply runs `BioUnlock.exe install` with the matching flags.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File uninstall-agent.ps1
```

This stops the tray, removes the start-at-login entry and the Start Menu
shortcut, and deletes `%LOCALAPPDATA%\BioUnlock` (the app, config, device key,
stored Windows credential, replay DB, and logs). Use `-KeepData` to keep your
data, or `-RemoveCredentialProvider` to also remove the Credential Provider
(elevated). A boot-start service is removed separately with
`uninstall-service.ps1` (admin).

## Build the app

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

This builds the native Credential Provider (if the VS C++ toolchain is present)
and then uses PyInstaller (`BioUnlock.spec`) to produce a single
`dist\BioUnlock.exe` with no console window — with the provider DLL bundled
inside it, so the one file installs everything.

## Run from source (development)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m biounlock_agent tray
```

`pywin32` (DPAPI + Windows service) and `pystray`/`Pillow` (tray icon) come from
`requirements.txt`. The agent runs headless on non-Windows platforms for
development, without DPAPI or tray support.

## Host your backend

BioUnlock is **single-owner**: the backend in `../server` is meant to be hosted
and used by you alone. Deploy it anywhere that runs Python — for example
[Vercel](https://vercel.com) (serverless) or any small VM — and point both the
phone app and this Windows app at that URL. See
[`../docs/deploy-vercel.md`](../docs/deploy-vercel.md) for the environment
variables to set on the host (so no secrets ever live in the repo).

> **Security note:** registering a passkey and linking a PC both require your
> backend's `BIO_API_TOKEN`, so a stranger who learns the URL still cannot add a
> device or sign in. Keep the URL and the token private.

## Credential Provider (logon-screen unlock)

The native provider is built from `windows-credential-provider/`. The packaged
`.exe` **bundles its DLL** and registers it automatically during
`BioUnlock.exe install` (behind the one UAC prompt), so end users never build or
install it by hand.

To build and register it manually (for source checkouts or development):

```powershell
powershell -ExecutionPolicy Bypass -File windows-credential-provider\build.ps1
powershell -ExecutionPolicy Bypass -File windows-credential-provider\install.ps1   # needs admin
python -m biounlock_agent set-credential
```

## Command line

```powershell
python -m biounlock_agent tray             # system tray app (default with no args)
python -m biounlock_agent install          # copy into %LOCALAPPDATA%, autostart, shortcut, provider
python -m biounlock_agent enroll --server-url https://unlock.example.com --token <api-token> --name "Workstation"
python -m biounlock_agent run              # foreground agent
python -m biounlock_agent status           # local status as JSON
python -m biounlock_agent set-credential   # store the DPAPI-protected Windows credential
python -m biounlock_agent clear-credential # remove it and any pending ticket
python -m biounlock_agent unenroll         # remove local enrollment + device key
```

## Run as a Windows service

For unlocking before any user logs in, the pywin32 service wrapper is also
available:

```powershell
python -m biounlock_agent.service install
python -m biounlock_agent.service start
python -m biounlock_agent.service stop
python -m biounlock_agent.service remove
```

## How verification works

For each delivered envelope the agent checks, in order:

1. `server_signing_key_id` equals the pinned fingerprint.
2. The Ed25519 `signature` over
   `biounlock-envelope-v1|request_id|account_id|pc_id|operation|issued_at|expires_at|nonce`.
3. `pc_id` is this device.
4. `operation` is one of the allowed operations (`remote_unlock` or
   `remote_lock`).
5. Freshness (`expires_at`, `issued_at` within a small clock skew).
6. Replay: the `request_id`/`nonce` was not already processed (persistent
   SQLite dedupe).

Only an envelope that passes all checks is acknowledged `verified`; authentic
envelopes that fail semantics (expired, unsupported operation, clock skew) are
acknowledged `rejected` with a reason code. Anything whose signature cannot be
trusted is dropped silently. The agent never executes anything from an envelope.
`account_id` is a fixed placeholder (`biounlock`) — BioUnlock has no accounts.

## Files and protection

| Item | Location | Protection |
| --- | --- | --- |
| Device private key | `%LOCALAPPDATA%\BioUnlock\device_key.bin` | Windows DPAPI (current user) |
| Config (server URL, IDs, pinned key) | `%LOCALAPPDATA%\BioUnlock\config.json` | Non-secret |
| Windows credential (for unlock) | `%LOCALAPPDATA%\BioUnlock\windows_credential.bin` | Windows DPAPI (current user) |
| Replay database | `%LOCALAPPDATA%\BioUnlock\replay.sqlite3` | Non-secret |
| Agent log | `%LOCALAPPDATA%\BioUnlock\agent.log` | Non-secret |
| Pending unlock ticket | `%ProgramData%\BioUnlock\unlock_ticket.bin` | Windows DPAPI (machine) |

Set `BIOUNLOCK_AGENT_HOME` to override the per-user directory. On non-Windows
platforms a plaintext file store is used as a development fallback.

## Tests

```powershell
cd pc-agent
pip install -r requirements-dev.txt
pytest
ruff check .
```

The tests cover the crypto formats, envelope verification (including tampering,
expiry, and replay), config/secret storage, the API client, and the agent's
envelope-handling and pairing logic. No live server is required.
