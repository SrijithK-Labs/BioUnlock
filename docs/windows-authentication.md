# Windows Logon Integration (future milestone)

**Status: NOT IMPLEMENTED.** BioUnlock's initial MVP does not unlock the
Windows login screen. This document describes the plan and the constraints.

## What the MVP does

The PC agent verifies a signed authorization envelope and reports the result
truthfully (`verified` / `rejected`). Nothing is executed on the secure
desktop, nothing is typed into the logon UI, and no Windows credential is
stored or transmitted.

## What a future milestone would require

The supported mechanism to add an alternate way to sign in on Windows is a
**Credential Provider** — a COM in-process server written in native
C++ (V2 API) or C#/.NET that plugs into the LogonUI/secure desktop flow.

Constraints that the design must respect:

- A Credential Provider runs in the **secure desktop** on the logon UI at the
  moment the workstation is locked. It cannot depend on the user session's
  agent process being logged in interactively.
- BioUnlock should only *drive the credential provider to tell the user that a
  remote authorization succeeded*; it must not bypass Windows authentication.
  On supported systems the provider can invoke Winlogon's
  `WLLogonNotify` / `SidToLogonSession` APIs only through the documented
  provider interfaces. Any stored credential used must be protected with
  DPAPI and configurable account policy.
- The provider must not: inject passwords into the logon screen, simulate
  keyboard input, modify LSASS memory, or use undocumented APIs.
- The user must keep the normal Windows sign-in method available at all times
  (the provider is added, not replacing).

### Interface between the native provider and the Python agent

The Python agent runs in the user session and cannot control the secure
desktop directly. A realistic design:

1. The **agent** keeps watching verified envelopes (as it already does).
   On a *verified remote_unlock* it writes a **ticket** into a location both
   processes share with appropriate ACLs (e.g. `%ProgramData%\BioUnlock\`),
   containing a short-lived, high-entropy ticket ID (never the raw envelope).
2. The **credential provider** (running during the logon prompt) detects the
   new ticket, shows "Unlock approved on your phone — press Sign in", and on
   confirmation calls `WLLogonNotify(...)` via the documented provider
   credential interfaces with the account the ticket is bound to.
3. Windows performs its real authentication; BioUnlock provides only the
   "the user verified on their phone" signal, scoped to the ticket's account,
   TTL, and revocation status.

This is exactly the design space that must be implemented in a later
milestone, in a disposable Windows VM, and verified for real. Nothing about it
is implemented or claimed today.

## Safety invariants (unchanged across the whole project)

- Normal Windows sign-in always remains available.
- No Windows password is ever stored or transmitted.
- No keyboard/mouse injection into the logon UI.
- No LSASS tampering; no undocumented APIs.
- The agent fails closed when signature, freshness, or binding cannot be
  verified.