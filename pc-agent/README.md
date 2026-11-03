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

Download the prebuilt `BioUnlock-0.1.0-windows-x64.exe` from
[**Releases**](https://github.com/SrijithK-Labs/BioUnlock/releases) — you do not
need Python or any build tools. **The one `.exe` installs everything.**

1. Double-click the `.exe` (or run
   `BioUnlock-0.1.0-windows-x64.exe install` from a terminal). Because it is not
   installed yet, it opens a small setup wizard:
   **Welcome → Choose your setup → Install → Finish**. On the options page you
   can turn off sign-in unlock, start-at-login, the Start Menu shortcut, or the
   post-install launch. The wizard copies the app to `%LOCALAPPDATA%\BioUnlock`
   and shows each finished step. No admin rights are needed for those parts.
2. If you keep **Enable unlock at the Windows sign-in screen**, it then asks
   once for elevation (**one UAC prompt**) to do the two things that make
   logon-screen unlock work **after a restart or a shutdown**: register the bundled Windows
   Credential Provider (the component that signs you in at the real logon
   screen) and install a SYSTEM startup task that receives phone requests
   before anyone has signed in. Declining returns to the finish page with a
   **Retry** button; everything else still installs. The same step moves the
   agent's profile to `%ProgramData%\BioUnlock` so the startup task and the tray
   share one identity and one stored credential; an existing link, device key,
   and Windows password are migrated automatically, so you do not have to link
   the PC again.
3. Click the tray icon, enter your backend URL and the **API key**, then
   **Link this PC** and scan the QR code with the phone app.

   The API key **is required** here. Linking enrolls this PC through the
   backend's `POST /api/v1/devices/enroll` endpoint, which is protected by your
   backend's `BIO_API_TOKEN`, so someone who only knows your URL still cannot
   register a device. You only enter it once: the agent stores it
   (DPAPI-protected) and reuses it for future re-links. After pairing, the PC
   authenticates with its own signed device key, so the token is not sent again.
4. To unlock the actual Windows logon screen, store your Windows password with
   **Set Windows password…** in the tray menu (or
   `python -m biounlock_agent set-credential`).

For unattended/scripted installs, add `--silent` (or set
`BIOUNLOCK_INSTALLER_QUIET=1`); the wizard is skipped and the result is printed
to the console. Passing any `--no-*` flag also implies a scripted run.

### What runs when

| Situation | Who talks to the server |
| --- | --- |
| PC is at the sign-in screen (boot, or after a sign-out) | the `BioUnlockAgent` SYSTEM task running `%ProgramFiles%\BioUnlock\BioUnlock.exe service-run` |
| A user is signed in, including a locked desktop | the tray in that session; the startup task idles |

Only one of them normally runs the agent at a time. At sign-in the hand-off
takes a second or two; a brief overlap is harmless because both share one
replay store and locking is idempotent.

**Fast Startup.** Windows does not run at-startup tasks when a *shut down* is
followed by a Fast Startup resume, so the pre-login agent would be missing at
the sign-in screen. The installer therefore sets `HiberbootEnabled` to `0` and
reports it as a step. The setting is machine-wide and reversible:

```powershell
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' `
  -Name HiberbootEnabled -Value 1 -Type DWord
```

With Fast Startup back on, sign-in-screen unlock works after a **restart** but
not after a **shut down**.

If Windows **Smart App Control** blocks the unsigned `.exe`, install the source
launcher instead (it runs with `pythonw.exe`, which Smart App Control allows):

```powershell
powershell -ExecutionPolicy Bypass -File install-agent.ps1 -FromSource
```

`install-agent.ps1` remains available for scripted installs; for a packaged
`.exe` it runs `BioUnlock.exe install --silent` with the matching flags (no
wizard, no message boxes). The SYSTEM task executes only the protected copy in
`%ProgramFiles%\BioUnlock`; standard users have read/execute access there.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File uninstall-agent.ps1
```

This stops the tray, removes the start-at-login entry and the Start Menu
shortcut, and deletes `%LOCALAPPDATA%\BioUnlock` (the app, config, device key,
stored Windows credential, replay DB, and logs). It also removes the SYSTEM
pre-login task (one UAC prompt; pass `-KeepSystemAgent` to keep it), and
`-RemoveCredentialProvider` removes the Credential Provider and its protected
Program Files binaries as well. Use `-KeepData` to keep your per-user data.
Legacy source-installed services can be removed with `uninstall-service.ps1`;
new source-based LocalSystem service installs are disabled.

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

Source-based LocalSystem services are disabled because they could import code
from a user-writable source directory. Use the packaged installer for pre-login
unlock; its SYSTEM task runs a protected copy under `%ProgramFiles%`.

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
| Device private key | `%ProgramData%\BioUnlock\device_key.bin` | Windows DPAPI (machine) |
| Config (server URL, IDs, pinned key) | `%ProgramData%\BioUnlock\config.json` | Non-secret |
| Windows credential (for unlock) | `%ProgramData%\BioUnlock\windows_credential.bin` | Windows DPAPI (machine) |
| Replay database | `%ProgramData%\BioUnlock\replay.sqlite3` | Non-secret |
| Agent log | `%ProgramData%\BioUnlock\agent.log` | Non-secret |
| Pending unlock ticket | `%ProgramData%\BioUnlock\unlock_ticket.bin` | Windows DPAPI (machine) |

A per-user install that has not yet gone through the elevated step keeps the
same files under `%LOCALAPPDATA%\BioUnlock` with user-scope DPAPI. The installer
copies that profile across and re-protects the secrets, because the SYSTEM
startup task cannot decrypt a per-user blob before that user signs in. Set
`BIOUNLOCK_AGENT_HOME` to override the directory. On non-Windows platforms a
plaintext file store is used as a development fallback.

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
