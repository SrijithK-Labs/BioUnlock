# BioUnlock Security

Initial-release security notes. See also `threat-model.md` and `protocol.md`.

## What protects credentials

- **Phone**: passkeys live in platform-secure storage; BioUnlock never sees the
  private key, never collects fingerprints/face images/biometric templates, and
  never uploads them.
- **PC**: the device Ed25519 private key and (for logon-screen unlock) the
  Windows credential are stored in files encrypted with Windows DPAPI. A per-user
  install keeps them in current-user scope under `%LOCALAPPDATA%\BioUnlock`; once
  the installer enables pre-login unlock it moves the profile to
  `%ProgramData%\BioUnlock` and re-protects them with **machine** scope, because
  the SYSTEM startup task has to decrypt them at the sign-in screen before any
  user exists. The directory ACL grants access only to SYSTEM, local
  administrators, and the installing Windows account. Machine-scope DPAPI means
  SYSTEM and local administrators can decrypt those files — a deliberate
  trade-off for unlocking before login, and the reason the PC itself must be
  trusted.
- **Server**: pairing codes are stored as SHA-256 hashes. Deployed environments
  require the Ed25519 signing key through `BIO_SIGNING_KEY` from a deployment
  secret store. The database contains passkey public credentials, device state,
  and authentication history, so protect it and its backups. Never deploy the
  SQLite development database publicly.

## Owner API token

Every owner endpoint — passkey registration and management, device
listing/revocation, pairing confirmation, security events, and authorization
requests — requires the shared secret `BIO_API_TOKEN`, sent as
`Authorization: Bearer <token>`. PC enrollment is gated the same way, so only
Someone who knows the deployment secret can add a device. The mobile app stores
the token in platform-secure storage and sends it on every owner call; the PC
agent uses it only for the one-time `enroll` request and afterwards
authenticates with its own signed device credential. Deployed environments
fail closed without `BIO_API_TOKEN`; only an explicitly enabled test harness
bypasses token checks. Generate one with
`python -c "import secrets; print(secrets.token_urlsafe(32))"` and set the same
value in the app's setup screen and in the PC agent (the Link dialog, or
`--token` / `BIOUNLOCK_AGENT_TOKEN`). The owner token is a long-lived shared
secret with no built-in expiry; rotate it immediately if exposed.

## PC agent authentication

The PC agent signs each request with its Ed25519 device credential. Signature
failures return a single generic `401` regardless of the reason — whether the
device id is unknown, revoked, expired, or simply mis-signed — so the API cannot
be used to probe which device ids exist. A device must be paired and active to
use the endpoints and open the agent WebSocket.

## Transport

- Production traffic is HTTPS-only. Certificate verification is **never**
  globally disabled.
- Packaged clients and Windows service installs require HTTPS. Mobile debug
  builds allow HTTP only for localhost or RFC1918 private IPv4 addresses. PC
  source runs require the explicit `BIOUNLOCK_ALLOW_INSECURE_HTTP=1` opt-in and
  only allow localhost or RFC1918 private addresses. Never use cleartext HTTP
  on an untrusted network.
- The PC agent pins the server signing key learned during pairing. Changing the
  backend URL removes the pinned identity and forces re-pairing; credentials
  are never forwarded to a new server automatically.

## Rate limiting

In-process per-IP limits and database-backed per-pairing-code attempt limits are
enabled by default and cannot be disabled outside the test harness. Multi-worker
or serverless deployments also need a shared edge/proxy limiter because
per-process counters are not global.

## Secrets-in-logs rules

Never log passwords, private keys, DPAPI material, bearer tokens, complete
WebAuthn assertions, or pairing codes. Sanitize URLs by stripping query strings.

## Operational guidance

- Run only what you can patch. Database backups: regular; restore test on a
  disposable machine before relying on it.
- Protect the signing key. If it is compromised, rotate it: re-pair all PCs.
- Firewall: the backend must accept inbound HTTPS (and WS on the same origin);
  PCs and phones need outbound HTTPS only. No inbound ports on the PC.
- Monitor health, failed logins, revoked devices, and error rates.

## Experimental warning

Windows logon unlocking is implemented but experimental. It stores a Windows
credential locally with DPAPI; SYSTEM and local administrators can decrypt it
when pre-login unlock is enabled. Use only on trusted machines, and do not rely
on this project to protect production accounts until the Windows flow has been
independently reviewed and tested on disposable Windows VMs.