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