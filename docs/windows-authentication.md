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
   (or, once the installer has switched the PC to the shared profile, *machine*
   scope at `%ProgramData%\BioUnlock\windows_credential.bin` — see "Pre-login
   support").
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

## Pre-login support (SYSTEM startup task)

The flow above runs in the user's session, so on its own it only works **after**
someone logs in. To unlock at the **sign-in screen after a restart**, the
installer also registers a Windows **scheduled task**, in the same single UAC
prompt that registers the provider:

| Property | Value |
| --- | --- |
| Task name | `BioUnlockAgent` |
| Run as | `SYSTEM`, highest privileges |
| Trigger | at startup |
| Action | `%ProgramFiles%\BioUnlock\BioUnlock.exe service-run` |
| Settings | no execution time limit, ignore new instances, restart 3× a minute after a failure |

`service-run` (`biounlock_agent/service.py`, `run_foreground`) is a small
supervisor loop, not a Windows service:

- it uses the machine-wide home `%ProgramData%\BioUnlock` with DPAPI
  **machine**-scope secrets, so the device key and Windows credential written
  by the in-session tray are readable before anyone logs in;
- it runs the agent **only while no session has a signed-in user**;
- a locked desktop and a disconnected RDP session both still count as signed
  in, so the tray keeps the agent and the task idles. Only a sign-out (or
  shutdown) hands control back to the task. At sign-in the hand-off takes at
  most a couple of seconds; a brief overlap is harmless because both agents
  share one replay store and the Windows lock is idempotent;
- if the agent exits unexpectedly it is restarted after a few seconds.

The `BioUnlock.exe install` step (the wizard's Install page) copies the agent
and credential provider to `%ProgramFiles%\BioUnlock` with SYSTEM/admin write
and standard-user read/execute permissions. It and `install-agent.ps1` perform
the profile move automatically: it copies
`config.json`, re-protects `device_key.bin`, `api_token.bin`, and
`windows_credential.bin` to machine scope, and writes the `service.json` marker
**last**. Until the marker exists the agent keeps using
the per-user directory, so an interrupted migration changes nothing. The
per-user files are kept for rollback, and an existing enrollment, link, and
stored Windows password carry over — **no re-linking and no repeated
`set-credential` are needed**.

The marker makes `config.service_mode()` true, so the tray transparently
switches to the shared home and machine-scope secrets too.

Source-based LocalSystem service installation is disabled. A service importing
Python code from a user-writable checkout would allow privilege escalation.
`uninstall-service.ps1` exists only to remove legacy installations safely.

To remove the packaged install, run `uninstall-agent.ps1`; it stops and
unregisters the `BioUnlockAgent` task (one UAC prompt, or pass
`-KeepSystemAgent` to keep it) and leaves `%ProgramData%\BioUnlock` in place so
the enrollment survives.

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
agent (tray, or the SYSTEM task before login)   provider (SYSTEM, secure desktop)
  verify envelope                                watch %ProgramData%\BioUnlock\
  -> write unlock_ticket.bin  ------------->       unlock_ticket.bin (machine DPAPI)
     (machine DPAPI, TTL)                          parse + validate TTL
                                                   CredentialsChanged -> auto-submit
```

## Security invariants

- Normal Windows sign-in always remains available.
- The Windows credential is stored **only** locally, DPAPI-protected, and is
  never transmitted; the server and phone never see it. With pre-login unlock
  enabled the protection is machine scope, so SYSTEM and local administrators on
  that PC can technically decrypt it. The shared directory ACL also grants
  access to the installing account, but not other standard Windows accounts.
- Tickets are short-lived and machine-scope DPAPI. The shared directory also
  contains long-term secrets, so its ACL is restricted to SYSTEM, local
  administrators, and the installing account.
- No keyboard/mouse injection into the logon UI.
- No LSASS tampering; no undocumented APIs.
- The agent fails closed when signature, freshness, or binding cannot be
  verified.

## Recovery

If the provider ever misbehaves, sign in with your password (always available),
or boot to Safe Mode and run
`pc-agent/windows-credential-provider/uninstall.ps1`. Remove the stored
credential with `python -m biounlock_agent clear-credential`.
