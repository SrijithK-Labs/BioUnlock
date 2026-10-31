# BioUnlock Authentication Protocol

This document specifies message formats, key ownership, signature
verification, and failure behaviour. Design principle: **never trust a request
just because it came from the backend.**

## Notation

- `||` = byte concatenation
- Ed25519 signatures are produced with `cryptography` (`cryptography.hazmat`).
- Timestamps are UTC seconds since epoch.
- DOT-notation JSON fields are used below; the exact wire encoding is the JSON
  objects returned by the endpoints described in `server/app/api`.

## Key ownership

| Key | Owner | Purpose |
| --- | --- | --- |
| User passkey (WebAuthn) | Phone | Proves the human to the server (RP) |
| Device keypair (Ed25519) | PC agent | Proves the PC to the server and signs PC->server messages |
| Server signing keypair (Ed25519) | Backend | Signs authorization envelopes trusted by PCs |

The PC agent learns and **pins** the server's public signing key during
pairing (via the enrollment handshake + QR). After that, any envelope that does
not verify against this pinned key is dropped. A changed server therefore
cannot forge envelopes for an already-paired PC.

## Passkey enrollment

`POST /api/v1/webauthn/register/begin` and `.../register/complete`, together with
`DELETE /api/v1/webauthn/credentials/{id}`, require
`Authorization: Bearer <BIO_API_TOKEN>`. Reading the credential list needs only
that token.

The first passkey may be registered with the API token alone. Once at least one
credential exists, the same calls also require
`X-BioUnlock-Enrollment: <BIO_ENROLLMENT_TOKEN>`. The second secret keeps a
leaked API token from enrolling an attacker's authenticator and unlocking every
paired PC. A deployment that already has a passkey refuses these calls when
`BIO_ENROLLMENT_TOKEN` is unset. The app sends the header only on passkey
changes, never on ordinary owner calls.

## Pairing / enrollment

1. Agent generates `(sk_pc, pk_pc)` locally. `sk_pc` is stored DPAPI-protected.
2. Agent → `POST /api/v1/devices/enroll` with `pk_pc`, device metadata, and
   `Authorization: Bearer <BIO_API_TOKEN>` (enrollment is owner-gated, so an
   anonymous client cannot create devices).
   Server responds: `{ device_id, pairing_code, qr_payload, expires_at, server_signing_pk }`.
   `pairing_code` is unpredictable, single-use, TTL `pairing_ttl`, with attempt
   limits.
3. UI shows the QR (contains base URL, pairing code, server fingerprint).
4. The owner proves user verification with the registered passkey, then the
  phone sends `POST /api/v1/pairing/confirm` with the pairing code. The
  server marks the device active and invalidates the pairing code.
5. Agent records `(device_id, server_base_url, pinned_server_signing_pk)`
   and starts operating. Any PC->server request is authenticated with
   `Authorization: Biounlock <device_id>.<expiry>.<sig>` where the signature is
  over `biounlock-device-auth-v1|server_fingerprint|device_id|expiry`, using
  `sk_pc`.

## Remote authentication request

### 1. Challenge (server)

`POST /api/v1/auth/challenges` body: `{ pc_id }`.

Response (`ChallengeResponse`):

```json
{
  "challenge_id": "uuid",
  "challenge": "base64url-32-random-bytes",
  "expires_at": 1700000000,
  "pc_id": "uuid",
  "pc_name": "Workstation",
  "rp_id": "example.com"
}
```

The challenge is stored server-side, single-use, and expires after
`challenge_ttl`.

### 2. Assertion (phone → server)

The app calls the platform authenticator to create a WebAuthn assertion using
`challenge` as the challenge bytes (the platform wraps it as needed per the
WebAuthn spec). It then submits:

`POST /api/v1/auth/requests`

```json
{
  "challenge_id": "uuid",
  "pc_id": "uuid",
  "operation": "remote_unlock",
  "assertion": { "id": "...", "rawId": "...", "type": "public-key",
                 "response": { "authenticatorData": "...", "clientDataJSON": "...",
                               "signature": "...", "userHandle": "..." } }
}
```

`operation` is one of the supported operations (`remote_unlock` or
`remote_lock`) and defaults to `remote_unlock` when omitted.

### 3. Server verification and envelope

1. The challenge is fetched, must match the submitted PC, be unexpired, and be
   unused. It is atomically consumed before assertion verification.
2. The WebAuthn assertion is verified with the maintained `webauthn` library
   against the registered credential and the consumed challenge.
3. The registered passkey proves the single owner; the target PC must be active
   and paired.
4. An `AuthRequest` row is created:
   `{ id, pc_id, challenge_id, operation, status: "pending", expires_at,
     created_at, nonce }`.
5. An **authorization envelope** is signed with the server signing key:

```
sign_message = "biounlock-envelope-v1" || request_id || "biounlock" || pc_id ||
               operation || issued_at || expires_at || nonce
```

Envelope JSON delivered to the agent:

```json
{
  "request_id": "uuid",
  "account_id": "biounlock",
  "pc_id": "uuid",
  "operation": "remote_unlock",
  "issued_at": 1700000000,
  "expires_at": 1700000120,
  "nonce": "uuid",
  "signature": "base64url-ed25519",
  "server_signing_key_id": "sha256-fingerprint"
}
```

### 4. Agent-side verification (independent)

The agent accepts the envelope **only if all** hold:

- `signature` verifies under the **pinned** server signing key with the exact
  signing message above, and the fingerprint matches;
- `pc_id` equals the agent's registered device id;
- `expires_at > now` (with small clock skew allowance);
- `request_id`/`nonce` were not already processed (persistent dedupe);
- `account_id` equals the protocol's single-owner value `biounlock`, and the
  agent is currently paired.

Failure → the agent rejects and drops the envelope (reason code, no secrets).
It **never** executes anything from the envelope other than a registered
operation (`remote_unlock` or `remote_lock`), and it never
treats mere delivery from the server as authorization to unlock a session.

### 5. Acknowledgment

`POST /api/v1/requests/{id}/ack` body: `{ status: "verified"|"rejected",
reason_code?, observed_at }`. The PC authenticates this request with its
short-lived signed device-authorization header.

A `verified` ack may still carry an informational `reason_code` so the phone can
report the true state: `already_unlocked` (the PC was not locked when an unlock
was approved) or `already_locked` (a lock was requested while already locked). A
failed lock is reported as `rejected` with `lock_failed`.

Server validates the active device credential and that the request targets that
device, then updates the request status. Terminal statuses: `rejected`,
`verified`, `expired`.
`expired` is set by a sweeper when `expires_at` passes while still pending.

### 6. Truthful status to the phone

`GET /api/v1/requests/{id}` returns the stored status. The UI displays what
the server actually knows. **A successful HTTP submit alone is never shown as
"succeeded/verified".**

## Replay protection

- Auth requests: `nonce` + `request_id` unique; agent persists processed ids.
- Pairing codes: single-use, attempt-limited, TTL.
- Challenges: single-use, TTL.
- PC->server auth: `expiry` + signature; server checks expiry and current
  device status.

## Throttling

- Registration and pairing: rate limited per IP; pairing-code attempts are
  counted in the database.
- Challenge creation: bounded.
- Acknowledgment: idempotent (same final status from same device accepted
  once; conflicting status → latest accepted with an audit event).

## Device revocation

`DELETE /api/v1/devices/{id}` (phone) or `POST /api/v1/devices/{id}/revoke`.
Server marks the device revoked, closes its active delivery sockets, and records
a `security_event`. Revoked devices cannot
ack or receive envelopes; pending requests targeting them fail closed.

## Freshness and failure behaviour

- Envelope expiry is enforced server-side (sweeper) and agent-side.
- A server outage means: no challenge, no envelope, no ack — requests fail
  closed. There is no offline unlock.