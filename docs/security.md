# BioUnlock Security

Initial-release security notes. See also `threat-model.md` and `protocol.md`.

## What protects credentials

- **Phone**: passkeys live in platform-secure storage; BioUnlock never sees the
  private key, never collects fingerprints/face images/biometric templates, and
  never uploads them.
- **PC**: the device Ed25519 private key is stored in a file encrypted with
  Windows DPAPI (current-user scope). Configuration lives in
  `%LOCALAPPDATA%\BioUnlock` on Windows.
- **Server**: session tokens are hashed (SHA-256) at rest; the server signing
  key is an Ed25519 key in a protected file (path configurable) or secrets
  vault; the SQLite dev DB must never be deployed publicly.

## Owner API token

Every owner endpoint — passkey registration and management, device
listing/revocation, pairing confirmation, security events, and authorization
requests — requires the shared secret `BIO_API_TOKEN`, sent as
`Authorization: Bearer <token>`. PC enrollment is gated the same way, so only
someone who knows the deployment secret can add a device. The mobile app stores
the token in platform-secure storage and sends it on every call; the PC agent
uses it only for the one-time `enroll` request and afterwards authenticates with
its own signed device credential. If the token is unset the API stays open,
which is only tolerated outside production: a production deploy without
`BIO_API_TOKEN` refuses owner endpoints so a misconfiguration fails closed
instead of exposing the API. Generate one with
`python -c "import secrets; print(secrets.token_urlsafe(32))"` and set the same
value in the app's setup screen and in the PC agent (the Link dialog, or
`--token` / `BIOUNLOCK_AGENT_TOKEN`).

## PC agent authentication

The PC agent signs each request with its Ed25519 device credential. Signature
failures return a single generic `401` regardless of the reason — whether the
device id is unknown, revoked, expired, or simply mis-signed — so the API cannot
be used to probe which device ids exist. A device must be paired and active to
use the endpoints and open the agent WebSocket.

## Transport

- Production traffic is HTTPS-only. Certificate verification is **never**
  globally disabled.
- HTTP (`http://`) is allowed only for explicit development hosts:
  `localhost`, `127.0.0.1`, and RFC1918 private addresses, and only when the
  client is in development mode.
- The PC agent pins the server signing key learned during pairing. Changing the
  backend URL removes the pinned identity and forces re-pairing; credentials
  are never forwarded to a new server automatically.

## Rate limiting

Included by default (per-IP and per-account buckets) for
registration/login/pairing/challenge endpoints. Disable only in tests.

## Secrets-in-logs rules

Never log: passwords, private keys, DPAPI material, session tokens, bearer
tokens, WebAuthn client data assertions in full, or pairing codes. Sanitize
URLs (strip query strings) in logs.

## Operational guidance

- Run only what you can patch. Database backups: regular; restore test on a
  disposable machine before relying on it.
- Protect the signing key. If it is compromised, rotate it: re-pair all PCs.
- Firewall: the backend must accept inbound HTTPS (and WS on the same origin);
  PCs and phones need outbound HTTPS only. No inbound ports on the PC.
- Monitor health, failed logins, revoked devices, and error rates.

## Experimental warning

This is an experimental release. It does not implement Windows session
unlocking, so it cannot be abused to bypass Windows sign-in. Treat remote
authentication results as advisory until the logon integration is implemented
and tested on a disposable Windows VM.