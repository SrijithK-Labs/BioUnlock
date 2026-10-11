# Threat Model

Trust boundaries and mitigation by threat for the initial MVP.

Assets: user identity, PC-agent identity/keys, server signing key, paired
device bindings, authentication request integrity, truthful status reporting.

## Threat: Replay attacks

An attacker replays a previously valid envelope or assertion.

- **Mitigation:** unique `request_id`/`nonce` per envelope; agent persists
  processed ids and rejects duplicates; challenges single-use with TTL; PC
  heartbeat auth carries signed expiry; server consumes challenges atomically.

## Threat: Stolen or compromised phone

The phone holds a passkey and can authorize remote unlock requests.

- **Mitigation:** platform biometric requirement enforced via `local_auth`
  guard + passkey user-presence; the user can revoke the phone's session and
  revoke paired PCs from the dashboard; security event history is surfaced to
  the user. We cannot prevent the platform auth from being bypassed if the
  device OS is compromised — documented limitation.

## Threat: Unauthorized pairing

An attacker tries to pair a PC to an account they do not control.

- **Mitigation:** pairing codes are 192-bit random, single-use, TTL-limited,
  attempt-limited, and must be confirmed by a WebAuthn-authenticated account
  holder using a phone that can also see the QR. Revocation removes an
  unapproved device.

## Threat: Malicious requests

An attacker fabricates an auth request.

- **Mitigation:** challenge bound to account+PC; assertion must verify against
  a registered credential; server enforces device ownership on every endpoint
  (a PC id is never trusted without an ownership + paired + not-revoked
  check). The agent independently verifies each envelope.

## Threat: Compromised backend

The server is fully or partially controlled by an attacker.

- **Mitigation:** the agent pins the server signing key at pairing time; a
  different/new server cannot forge envelopes. WebAuthn assertions are verified
  against credentials stored by the (possibly compromised) server, so scope:
  a fully compromised backend can impersonate the user to the agent for as long
  as it holds the account credentials and device bindings. This is why the
  server must be treated as trusted infrastructure (TLS, secrets, auditing).
  Pairing re-pins the key in response to a suspected compromise.

## Threat: Agent impersonation

An attacker pretends to be a paired PC.

- **Mitigation:** the agent authenticates every API call and ack with an
  Ed25519 signature from its registered device key; the server checks
  `device_id`, signature, expiry, and status. Private keys stay in DPAPI
  storage.

## Threat: Credential theft

Session tokens, signing keys, or pairing codes are stolen.

- **Mitigation:** tokens hashed at rest, short TTL; signing keys stored with
  file/keyring protection; pairing codes ephemeral and single-use; secrets
  never logged or committed; `.env`/key files gitignored.

## Threat: Session hijacking

A stolen bearer token is replayed.

- **Mitigation:** HTTPS-only, token TTL + server-side revocation list; changing
  the backend invalidates local sessions and requires fresh pairing.

## Threat: Brute-force attacks

Passwords or pairing codes are guessed.

- **Mitigation:** bcrypt password hashing, global per-IP and per-account rate
  limits, pairing attempt caps, single-use codes, lockout-style backoff on
  repeated failures.

## Threat: Expired challenges

Stale challenges are used.

- **Mitigation:** server TTL (challenge, pairing, envelope), single-use
  consumption, sweeper transitions `pending` requests to `expired`.

## Threat: Revoked devices

A revoked/removed PC or session is still used.

- **Mitigation:** revocation marks rows and disconnects delivery sockets;
  revoked devices get 401/403 and dropped envelopes; revocation is logged.

## Threat: Network interruption

Temporary loss of connectivity breaks the flow.

- **Mitigation:** agent reconnect loop with bounded backoff; pending envelopes
  survive reconnects; requests expire if unresolved; retries are idempotent
  (ack by id). Requests fail closed when the server is unreachable.

## Threat: Account confusion

Cross-user access, e.g., user A controls user B's PC or requests.

- **Mitigation:** every protected endpoint checks account ownership of devices,
  challenges, requests, and security events before acting; tests cover
  cross-user prevention.

## Threat: Denial of service

The backend or agent is flooded.

- **Mitigation:** rate limiting, request size limits, bounded retry/backoff,
  small surfaces (no shell/cmd execution on the PC). The agent ignores unknown
  envelope formats.

## Threat: Backend URL substitution

A user is tricked into pointing clients at a malicious server.

- **Mitigation:** pairing pins server identity; changing the URL requires
  confirmation and re-pairing; no stored credentials are auto-forwarded to a
  new server; health checks are not treated as proof of trust; HTTPS-only in
  production; safe URL validation (scheme/host) on both clients.

## Threat: Local Windows privilege boundaries

A low-privilege local attacker reads agent secrets or hijacks the agent.

- **Mitigation:** DPAPI user-scoped encryption, restricted file ACLs on config
  and ticket store, service runs under a dedicated low-privilege account, GUI
  and service are separate processes, no arbitrary command execution surface.
  A user-level attacker on the same Windows account retains full access to that
  account's data regardless of BioUnlock — documented boundary.

## Non-goals of the MVP

- No Windows session unlock (see `windows-authentication.md`).
- No offline unlock when the backend is unreachable.
- No protection once the server host or the Windows account itself is fully
  compromised.