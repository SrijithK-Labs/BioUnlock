# BioUnlock Windows Credential Provider

Native (C++) credential provider that unlocks the Windows lock screen when the
paired phone approves a request. It is **added** to the normal sign-in options;
the built-in password tile always remains.

## How it works

1. The Python agent (in your user session) stores your Windows credential with
   **DPAPI in current-user scope** (`%LOCALAPPDATA%\BioUnlock\windows_credential.bin`).
   It is never sent to the server and never logged.
2. When the server delivers a **verified** `remote_unlock`, the agent mints a
   short-lived (default 60 s), single-use ticket at
   `%ProgramData%\BioUnlock\unlock_ticket.bin`, protected with **DPAPI machine
   scope** so the provider can read it.
3. This provider runs inside LogonUI on the secure desktop. Its watcher notices
   the ticket, tells LogonUI to re-enumerate, and the tile auto-submits the
   credential, which Windows validates normally (`KERB_INTERACTIVE_UNLOCK_LOGON`
   via the Negotiate/MSV1_0 package).
4. The ticket expires on its own; a stale or forged file is rejected (wrong
   DPAPI scope, bad magic, or expired timestamp).

The provider never injects input, never touches LSASS, and uses only documented
provider/`LsaLogonUser` interfaces.

## Build

Requires Visual Studio 2022 Build Tools with the Desktop C++ workload and a
Windows SDK.

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Output: `build\BioUnlockProvider.dll` (x64).

## Self-test (no install, no lock)

`tests\selftest.cpp` loads the built DLL, instantiates the provider through
`DllGetClassObject`, and drives `GetCredentialCount` / `GetSerialization`. With a
valid ticket in `%ProgramData%\BioUnlock` it reports the credential and the
serialized buffer; without one it offers nothing. This validates the COM
plumbing without registering anything or touching the lock screen.

## Install / uninstall (administrator)

```powershell
# elevated PowerShell
powershell -ExecutionPolicy Bypass -File install.ps1
python -m biounlock_agent set-credential      # as your own user, stores the password

# remove
powershell -ExecutionPolicy Bypass -File uninstall.ps1
python -m biounlock_agent clear-credential
```

## Security trade-offs

- The Windows password **is** stored locally (DPAPI current-user scope), a
  deliberate departure from the MVP rule "no Windows password is ever stored".
  It is required for a real unlock and is documented in
  `docs/windows-authentication.md`.
- While a ticket exists (seconds), it is readable by SYSTEM/Administrators and,
  because tickets are machine-scope DPAPI, by any local process on the machine.
  It is short-lived and single-use to limit this window.
- `%ProgramData%\BioUnlock` is writable by `Users` so the per-user agent can
  publish tickets; it holds no long-term secret.

## Recovery

The password tile is never removed. If the provider misbehaves, sign in with
your password, or boot into Safe Mode and run `uninstall.ps1`.
