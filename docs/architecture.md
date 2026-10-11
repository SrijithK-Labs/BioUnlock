# BioUnlock Architecture

This document describes the components, trust boundaries, and data flow of
BioUnlock. Read it together with `protocol.md`.

## Goal

Allow a user to prove who they are with a phone (WebAuthn passkey) and have a
paired Windows PC verify an authorization request, over the public Internet,
without inbound ports or shared Wi-Fi/Bluetooth.

## Components

```
┌──────────────────┐     HTTPS      ┌─────────────────────┐     HTTPS + WS(outbound)
│  Flutter app     │ ─────────────> │  FastAPI backend    │ <──────────────────┐
│  (Android phone) │                │  (you host)         │                    │
│  - passkey       │                │  - accounts         │    ┌──────────────┴───────────┐
│  - biometric     │ <───────────── │  - pairing          │    │  Windows PC agent         │
└──────────────────┘     HTTPS      │  - requests/signing │    │  - device ID (Ed25519)    │
                                    │  - delivery         │    │  - pinned server key      │
                                    └─────────────────────┘    │  - verifier               │
                                                               └───────────────────────────┘
```

- **Phone**: authenticates the human via the platform passkey provider
  (biometric-backed WebAuthn). The server is the WebAuthn Relying Party (RP).
- **Backend**: authorizes the user, resolves the target PC, creates
  cryptographically signed authorization envelopes, and delivers them to the
  PC agent. It never knows the Windows password and never unlocks Windows.
- **PC agent**: owns its device identity, keeps the server's signing key
  pinned, verifies every request independently, and reports a truthful result.

## Trust boundaries

| Boundary | Trust mechanism |
| --- | --- |
| Phone → Server | TLS + WebAuthn passkey assertion verified by the server |
| Server → Phone | TLS; server authenticity is a trust-on-first-use decision by the user when they enter the URL / scan a pairing QR |
| PC Agent → Server | TLS + device Ed25519 signature on every authenticated API call + per-session token |
| Server → PC Agent | Ed25519 signature over each authorization envelope, verified against a pinned server public key captured during pairing |
| Phone → PC Agent | No direct channel; the agent only trusts a signed envelope from the server that binds account, PC, request id, and expiry |

The **server signing key** is the root of truth for the PC agent. It is pinned
exactly once during the enrollment/pairing flow, together with the backend URL.
Changing the backend URL breaks the pinned server identity and forces a new
pairing — the PC agent will not accept requests from a server it did not pair
with.

## Data flow: remote authentication request

1. **Phone** (authenticated, WebAuthn user) requests a challenge for a target
   PC: `POST /api/v1/auth/challenges`.
2. **Server** stores a challenge (random bytes, expiry, client data) and returns
   it bound to account + PC.
3. **Phone** prompts the user with the platform passkey provider, then submits
   the assertion: `POST /api/v1/auth/requests`.
4. **Server** verifies the WebAuthn assertion, authorizes account→PC ownership,
   creates an `AuthRequest` (unique id, account, PC, challenge, expiry,
   status=pending), and signs an *authorization envelope* with its Ed25519 key.
5. **Delivery**: if the agent has an open outbound WebSocket, the envelope is
   pushed. On reconnect, pending envelopes are pulled. No inbound ports.
6. **PC agent** verifies the envelope signature against the pinned server key,
   checks identifiers (its registered PC id, account match), expiry, and
   replay/nonce. Then it proves the local "action condition" (currently: the
   verified/delivered state, since native Windows logon is a later milestone).
7. **PC agent** acks `POST /api/v1/requests/{id}/ack` → status `verified`
   (or rejects → `rejected`).
8. **Phone** polls `GET /api/v1/requests/{id}` until a terminal status and
   shows a truthful result ("Verified by PC", "Rejected", "Expired").

## Failure handling

- Server unreachable → the phone cannot authorize and the agent cannot
  receive; no request is accepted. Fail closed.
- Envelope expired → rejected.
- Envelope replayed/duplicate → rejected (unique id + nonce cache).
- Device revoked / unpaired → agent rejects; server stops delivery.
- Reconnect: the agent re-establishes WebSocket and re-registers presence.

## Key storage

| Secret | Where | Protection |
| --- | --- | --- |
| Passkey private keys | Phone TPM/secure element | platform (never in BioUnlock) |
| Server signing key | Backend filesystem/env | file permissions; configurable path |
| PC device private key | Windows machine | DPAPI-protected file |
| Session tokens | Backend DB | hashed at rest |