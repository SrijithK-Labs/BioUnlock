# Threat Model

Trust boundaries and mitigation by threat for the initial MVP.

Assets: owner identity, PC-agent identity/keys, server signing key, paired
device bindings, authentication request integrity, truthful status reporting.

## Threat: Replay attacks

An attacker replays a previously valid envelope or assertion.

- **Mitigation:** unique `request_id`/`nonce` per envelope; agent persists
  processed ids and rejects duplicates; challenges single-use with TTL; PC
  heartbeat auth carries signed expiry; server consumes challenges atomically.

## Threat: Stolen or compromised phone

The phone holds a passkey and can authorize remote unlock requests.

- **Mitigation:** WebAuthn requires user verification on the platform
  authenticator; the owner can revoke paired PCs and review security events.
  BioUnlock cannot protect a phone after its operating system is compromised.

## Threat: Unauthorized pairing

An attacker tries to pair an unapproved PC without the owner's passkey.

- **Mitigation:** pairing codes are 128-bit random, single-use, TTL-limited,
  attempt-limited, and must be confirmed by the owner's WebAuthn passkey using
  a phone that can also see the QR. Revocation removes an
  unapproved device.

## Threat: Malicious requests

An attacker fabricates an auth request.

- **Mitigation:** challenge bound to a specific PC; assertion must verify
  against the owner's registered credential; the target PC must be active and
  paired. The agent independently verifies each signed envelope.

## Threat: Compromised backend

The server is fully or partially controlled by an attacker.

- **Mitigation:** the agent pins the server signing key at pairing time; a
  different/new server cannot forge envelopes. WebAuthn assertions are verified
  against credentials stored by the (possibly compromised) server, so scope:
  a fully compromised backend can impersonate the owner to the agent for as long
  as it controls the passkey public credentials and device bindings. This is why the
  server must be treated as trusted infrastructure (TLS, secrets, auditing).
  Pairing re-pins the key in response to a suspected compromise.

## Threat: Agent impersonation

An attacker pretends to be a paired PC.

- **Mitigation:** the agent authenticates every API call and ack with an
  Ed25519 signature from its registered device key; the server checks
  `device_id`, signature, expiry, and status. Private keys stay in DPAPI
  storage.

## Threat: Credential theft

The owner API token, the enrollment token, a device key, the server signing key,
or a pairing code is stolen.

- **Mitigation:** device keys use DPAPI; pairing codes are high-entropy,
  single-use, short-lived, and stored as hashes. Production signing keys come
  from a deployment secret store. The owner API token is a long-lived shared
  secret and must be rotated immediately if exposed; it is not a revocable
  per-session token. Secrets must never be logged or committed.

## Threat: Owner API token replay

A stolen owner bearer token is replayed.

- **Mitigation:** HTTPS-only and secret-store protection. Rotate the shared
  token to revoke it. The token has no built-in expiry or per-session
  revocation; mobile storage uses platform secure storage. Once a passkey
  exists, registering another one also needs `BIO_ENROLLMENT_TOKEN`, so a
  stolen API token alone cannot add an attacker-controlled authenticator.

## Threat: Brute-force attacks

Pairing codes or owner tokens are guessed.

- **Mitigation:** pairing codes contain 128 bits of randomness, expire, are
  single-use, and have database-backed attempt caps. In-process per-IP limits
  are enabled; production deployments also need a shared edge/proxy limiter.

## Threat: Expired challenges

Stale challenges are used.

- **Mitigation:** server TTL (challenge, pairing, envelope), single-use
  consumption, sweeper transitions `pending` requests to `expired`.

## Threat: Revoked devices

A revoked/removed PC is still used.

- **Mitigation:** revocation marks rows and disconnects delivery sockets;
  revoked devices get 401/403 and dropped envelopes; revocation is logged.

## Threat: Network interruption

Temporary loss of connectivity breaks the flow.

- **Mitigation:** agent reconnect loop with bounded backoff; pending envelopes
  survive reconnects; requests expire if unresolved; retries are idempotent
  (ack by id). Requests fail closed when the server is unreachable.

## Threat: Device/request confusion

A request or acknowledgement is applied to a different paired PC.

- **Mitigation:** challenges are bound to a specific active device, signed
  envelopes include that device id, and acknowledgements require that device's
  signed credential. Tests cover cross-device rejection.

## Threat: Denial of service

The backend or agent is flooded.

- **Mitigation:** a 1 MiB request-body cap, rate limiting, bounded retry/backoff,
  small surfaces (no shell/cmd execution on the PC). The agent ignores unknown
  envelope formats.

## Threat: Backend URL substitution

A user is tricked into pointing clients at a malicious server.

- **Mitigation:** pairing pins server identity; changing the URL requires
  confirmation and re-pairing; no stored credentials are auto-forwarded to a
  new server; health checks are not treated as proof of trust; HTTPS-only in
  production; safe URL validation (scheme/host) on both clients.

## Threat: Local Windows privilege boundaries

A different, standard Windows account attempts to read agent secrets or forge
an unlock ticket.

- **Mitigation:** the shared data directory is ACL-restricted to SYSTEM, local
  administrators, and the installing account; Windows DPAPI protects stored
  blobs. The pre-login agent runs as SYSTEM, so local administrators and SYSTEM
  remain trusted and can decrypt machine-scope blobs. A process running as the
  installing user retains access to that user's data.

## Non-goals

- No offline unlock when the backend is unreachable.
- No protection once the server host or the Windows account itself is fully
  compromised.