# Security Policy

BioUnlock is an **experimental, self-hosted** authentication project, built for
personal machines. Your Windows password always remains a working sign-in
option, and Safe Mode recovery is documented, so a failure of BioUnlock cannot
lock you out of your own PC.

It has **not been independently audited**. Treat it as you would any young
security tool: fine to run and learn with, and fine as an everyday convenience,
but do not make it the *only* credential on a machine where a lockout would be
unrecoverable — for example a company laptop whose recovery keys are held by
someone else, or a server you cannot physically reach.

That paragraph is about maturity and about the backend you host yourself. It is
not a warning about a known defect: the cryptographic protocol (signed
single-use envelopes, replay protection, key pinning) is described in
[`docs/protocol.md`](docs/protocol.md) and the mitigations are listed in
[`docs/threat-model.md`](docs/threat-model.md).

## Where your data lives

Nothing secret is ever sent to a third party. BioUnlock has no analytics, no
telemetry, and no cloud of its own.

### On the Windows PC

| Data | Location | Protection |
| --- | --- | --- |
| Windows password (used to complete unlock) | `%ProgramData%\BioUnlock\windows_credential.bin` | Windows DPAPI, machine scope. Stays on the PC — never sent to the server or the phone. |
| Device private key | `%ProgramData%\BioUnlock\device_key.bin` | Windows DPAPI, machine scope |
| Pending unlock ticket | `%ProgramData%\BioUnlock\unlock_ticket.bin` | Windows DPAPI; single-use, 60 s lifetime by default |
| Config (server URL, IDs, pinned server key) | `%ProgramData%\BioUnlock\config.json` | Not secret |
| Replay-protection database, agent log | `%ProgramData%\BioUnlock\replay.sqlite3`, `agent.log` | Not secret |

A per-user install that has not yet run the elevated setup step keeps the same
files under `%LOCALAPPDATA%\BioUnlock` with user-scope DPAPI; the installer
migrates and re-protects them.

### On the Android phone

| Data | Location | Protection |
| --- | --- | --- |
| Server URL, API token, enrollment token | App storage via `flutter_secure_storage` | Android Keystore-backed encryption |
| Passkey private key | Android platform authenticator (Keystore/TEE) | Managed by Android; BioUnlock never sees the key |

### On the backend you host

| Data | Location | Protection |
| --- | --- | --- |
| Server signing key, owner API token, enrollment token | `BIO_SIGNING_KEY`, `BIO_API_TOKEN`, `BIO_ENROLLMENT_TOKEN` environment variables, and the server configuration row | Your deployment secret store — never committed to git |
| Paired devices, passkey public keys, audit events | Your Postgres database | Your database |

## What BioUnlock does not do

- It never collects, stores, or transmits raw biometric data. Fingerprint and
  face checks run in Android's platform authenticator.
- It does not implement Windows logon bypass. The credential provider supplies a
  real credential that Windows validates, and the built-in password tile is
  always available.
- It does not forward your Windows password to the server or the phone, and it
  never logs secrets.
- The PC agent opens no inbound ports and executes nothing from an unlock
  message; each signed envelope is verified on the PC itself.
- There is no account system, no session cookie, and no third-party service in
  the unlock path.

## Known trust boundaries

Worth knowing before you deploy, all documented in
[`docs/threat-model.md`](docs/threat-model.md):

- **Your backend is trusted infrastructure.** Because clients verify passkeys
  against the credential list the server holds, a *fully compromised* backend
  could impersonate you to a paired PC for as long as it controls that list.
  Pin `BIO_RP_ID`, keep `BIO_SIGNING_KEY` secret, and use HTTPS.
- **Administrators on the PC are trusted.** DPAPI protects the stored Windows
  credential from other standard users, but SYSTEM and local administrators can
  decrypt machine-scope blobs.
- **The owner API token is long-lived.** It has no per-session revocation; rotate
  it immediately if exposed. A stolen token on its own cannot register a new
  passkey once one exists, because `BIO_ENROLLMENT_TOKEN` is also required.

## Supported versions

The latest release ([`v1.0.0`](https://github.com/SrijithK-Labs/BioUnlock/releases/tag/v1.0.0))
and the current default branch are supported. Older commits and local builds are
not.

## Reporting a vulnerability

Please report security issues privately — never in a public issue.

1. Use GitHub's private vulnerability reporting on this repository
   (**Security** → **Report a vulnerability**). If that is unavailable, open a
   minimal public issue asking for a private contact channel — without exploit
   details.
2. Include:
   - A description of the issue and its impact.
   - Affected component(s) and version/commit.
   - A minimal reproduction, if possible.
   - Any suggested remediation, if you have one.
3. Do not share the details publicly until maintainers have acknowledged and
   addressed the report.

Maintainers aim to acknowledge reports within 7 days and to provide an
assessment and remediation timeline.

## Security expectations for contributors

- Never commit `.env`, private keys, certificates, keystores, or production
  credentials.
- Only HTTPS should be used to talk to production BioUnlock backends.
- Do not hardcode backend URLs; all servers are user-configurable.
- Do not invent cryptographic protocols; prefer maintained libraries.
- Security-relevant changes get a corresponding entry in
  [`docs/threat-model.md`](docs/threat-model.md) and
  [`docs/security.md`](docs/security.md).
