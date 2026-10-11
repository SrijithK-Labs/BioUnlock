# Windows Logon Integration

**Status: IMPLEMENTED (Option A — DPAPI-protected credential).** BioUnlock can
unlock the Windows lock screen when the paired phone approves a request. Two
pieces implement this:

- the Python agent (`biounlock_agent/unlock.py`, `set-credential` command), and
- a native **Credential Provider** (`pc-agent/windows-credential-provider/`).

> **Policy note.** A real unlock of a password-protected account requires the
> provider to supply a credential Windows accepts. This milestone therefore
> stores the user's Windows credential **locally** with DPAPI, which consciously
> departs from the earlier MVP rule "no Windows password is ever stored". The
> credential never leaves the machine and is never transmitted to the server or
> the phone. See "Security invariants" below.

## Flow

1. **Enrollment (once, user session).** `python -m biounlock_agent set-credential`
   prompts for the Windows password and stores it DPAPI-protected in
   *current-user* scope at `%LOCALAPPDATA%\BioUnlock\windows_credential.bin`
   (or, when the boot-start service is installed, *machine* scope at
   `%ProgramData%\BioUnlock\windows_credential.bin` — see "Pre-login support").
2. **Approval.** The phone approves a `remote_unlock`. The agent verifies the
   server-signed envelope exactly as before (signature, PC binding, freshness,
   replay) and acknowledges it `verified`.
3. **Ticket.** On a *verified* `remote_unlock` the agent writes a short-lived
   (default 60 s, capped 300 s), single-use ticket to
   `%ProgramData%\BioUnlock\unlock_ticket.bin`, protected with DPAPI *machine*
   scope. The ticket is a fixed little-endian record (never JSON, never the raw
   envelope): `request_id`, account, timestamps, and the credential.
4. **Unlock.** The Credential Provider (running as SYSTEM in LogonUI on the
   secure desktop) watches that file. On a valid ticket it asks LogonUI to
   re-enumerate; the BioUnlock tile becomes the default and auto-submits via
   `KERB_INTERACTIVE_UNLOCK_LOGON`, and **Windows performs its normal
   authentication** through the Negotiate/MSV1_0 package.
5. **Lock (optional).** A verified `remote_lock` needs no credential or ticket:
   the agent calls `LockWorkStation()` directly (reporting `already_locked` when
   the workstation is already locked, or `lock_failed` on error).

## Pre-login support (boot-start service)

The flow above runs in the user's session, so it only works **after** someone
logs in. To unlock at the **sign-in screen after a reboot**, BioUnlock installs
the agent as a boot-start Windows service (`biounlock_agent/service.py`) that:

- runs as **LocalSystem** and starts before anyone signs in;
- uses the machine-wide home `%ProgramData%\BioUnlock` with DPAPI **machine**-scope
  secrets, so the device key and Windows credential written by the in-session tray
  are readable before login;
- runs the agent **only while no interactive user is signed in**. When a user logs
  on it hands control to the tray, which is the only process that can lock the
  interactive desktop. The two never run at once.

Install / uninstall (both require an **elevated** PowerShell):

```powershell
# from pc-agent/
powershell -ExecutionPolicy Bypass -File install-service.ps1
powershell -ExecutionPolicy Bypass -File uninstall-service.ps1
```

`install-service.ps1` creates `%ProgramData%\BioUnlock` (SYSTEM/Administrators
full, Users modify), writes the `service.json` marker, and registers/starts the
`BioUnlockAgent` service. The marker makes `config.service_mode()` true, so the
tray transparently switches to the shared home and machine-scope secrets too.

Because the home moves, **re-link the tray and re-run `set-credential` once after
installing**, then reboot and unlock from the phone at the sign-in screen.

## Trust and failure rules

- The provider is **added, not replacing**: the built-in password tile is always
  present, so a user can always sign in normally.
- Tickets are bound to a request id, carry their own expiry, and are single-use.
- A stale, truncated, wrong-scope, or forged ticket is discarded
  (`ReadUnlockTicket` returns nothing); the agent fails closed on any envelope
  that is not fully verified.
- No input injection, no LSASS tampering, no undocumented APIs.

## Interface between the native provider and the Python agent

```
agent (user session)                         provider (SYSTEM, secure desktop)
  verify envelope                              watch %ProgramData%\BioUnlock\
  -> write unlock_ticket.bin  ------------->     unlock_ticket.bin (machine DPAPI)
     (machine DPAPI, TTL)                        parse + validate TTL
                                                 CredentialsChanged -> auto-submit
```

## Security invariants

- Normal Windows sign-in always remains available.
- The Windows credential is stored **only** locally, DPAPI-protected, and is
  never transmitted; the server and phone never see it.
- Tickets are short-lived and machine-scope DPAPI; the machine-wide ticket
  directory holds no long-term secret.
- No keyboard/mouse injection into the logon UI.
- No LSASS tampering; no undocumented APIs.
- The agent fails closed when signature, freshness, or binding cannot be
  verified.

## Recovery

If the provider ever misbehaves, sign in with your password (always available),
or boot to Safe Mode and run
`pc-agent/windows-credential-provider/uninstall.ps1`. Remove the stored
credential with `python -m biounlock_agent clear-credential`.
