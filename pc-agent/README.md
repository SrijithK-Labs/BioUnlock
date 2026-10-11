# BioUnlock PC agent

Outbound-only Windows agent. It pairs a PC with your BioUnlock backend, pins the
server's Ed25519 signing key, independently verifies every signed authorization
envelope, and reports a truthful result. It never opens an inbound port and never
stores or transmits a Windows password.

> **Status: experimental.** This milestone verifies requests and reports status.
> It does **not** unlock the Windows logon screen yet (see
> `../docs/windows-authentication.md`).

## Requirements

- Python 3.11+ on Windows (the agent also runs on other platforms for
  development, without DPAPI).
- The backend from `../server` reachable over HTTPS.

## Install

```powershell
cd pc-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`pywin32` (DPAPI + Windows service) and `PySide6` (GUI) are listed in
`requirements.txt`. Only the core dependencies (`cryptography`, `httpx`,
`websockets`, `pydantic`) are needed to run the agent headless.

## Enroll and run (CLI)

```powershell
python -m biounlock_agent enroll --server-url https://unlock.example.com --name "Workstation"
# scan the printed QR code (or type the pairing code) in the phone app

python -m biounlock_agent run        # foreground agent
python -m biounlock_agent status     # local status as JSON
python -m biounlock_agent unenroll   # remove local enrollment + device key
```

## Setup GUI

```powershell
python -m biounlock_agent gui
```

Enter the server URL, click **Enroll this PC**, scan the QR code with the phone,
then **Start agent**.

## Run as a Windows service

```powershell
python -m biounlock_agent.service install
python -m biounlock_agent.service start
# ...
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
trusted is dropped silently. `remote_unlock` mints a short-lived single-use
ticket for the Credential Provider; `remote_lock` locks the workstation (a
no-op reported as `already_locked` when it is already locked). The agent never
executes anything from an envelope.

## Files and protection

| Item | Location | Protection |
| --- | --- | --- |
| Device private key | `%LOCALAPPDATA%\BioUnlock\device_key.bin` | Windows DPAPI (current user) |
| Config (server URL, IDs, pinned key) | `%LOCALAPPDATA%\BioUnlock\config.json` | Non-secret |
| Replay database | `%LOCALAPPDATA%\BioUnlock\replay.sqlite3` | Non-secret |
| Service log | `%LOCALAPPDATA%\BioUnlock\agent.log` | Non-secret |

Set `BIOUNLOCK_AGENT_HOME` to override the directory. On non-Windows platforms a
plaintext file store is used as a development fallback.

## Tests

```powershell
cd pc-agent
pip install -r requirements-dev.txt
pytest
ruff check biounlock_agent tests
```

The tests cover the crypto formats, envelope verification (including tampering,
expiry, and replay), config/secret storage, the API client, and the agent's
envelope-handling and pairing logic. No live server is required.
