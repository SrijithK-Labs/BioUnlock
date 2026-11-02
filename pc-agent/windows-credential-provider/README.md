# BioUnlock Windows Credential Provider

<p align="center">
  <img src="../../logo/logo.png" alt="BioUnlock logo" width="110" />
</p>

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
valid ticket in `%ProgramData%\BioUnlock` it reports the credential count and
serialization size; without one it offers nothing. It does not print the
serialized credential. This validates the COM plumbing without registering
anything or touching the lock screen.

## Install / uninstall (administrator)

```powershell
# elevated PowerShell
powershell -ExecutionPolicy Bypass -File install.ps1
python -m biounlock_agent set-credential      # as your own user, stores the password

# remove
powershell -ExecutionPolicy Bypass -File uninstall.ps1
python -m biounlock_agent clear-credential
```

If the elevated PowerShell runs under a different administrator account, pass
the intended user's SID with `-InstallUserSid`; obtain it with `whoami /user` in
that user's session. The packaged installer captures the original user SID
before requesting elevation.

## Security trade-offs

- The Windows password **is** stored locally (DPAPI current-user scope), a
  deliberate departure from the MVP rule "no Windows password is ever stored".
  It is required for a real unlock and is documented in
  `docs/windows-authentication.md`.
- While a ticket exists (seconds), SYSTEM, local administrators, and the
   installing account can access it. Machine-scope DPAPI is not a boundary
   against those principals.
- `%ProgramData%\BioUnlock` is ACL-restricted to SYSTEM, local administrators,
   and the installing account. It contains long-term machine-scope secrets as
   well as the short-lived ticket.

## Recovery

The password tile is never removed. If the provider misbehaves, sign in with
your password, or boot into Safe Mode and run `uninstall.ps1`.
