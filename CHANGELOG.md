# Changelog

Notable changes to BioUnlock. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and release tags use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

BioUnlock ships three components with independent version numbers, so each
release lists the versions it contains. The tag (`v1.0.0`) is the release
version; it is not necessarily the version of every component.

## [Unreleased]

Nothing yet.

## [1.0.1] - 2026-11-03

Fixes for the pre-login unlock path (the Windows sign-in screen).

**Components:** Windows agent `1.0.1`. The Android app (`1.0.0`) and the
backend (`0.2.1`) are unchanged from `1.0.0`.

### Fixed

- Phone unlock did nothing at the Windows sign-in screen after a shut down or a
  restart, while it worked once a user was signed in. The session probe called
  `win32ts.WTSEnumerateSessions` with arguments that this pywin32 build rejects
  (error 87), and the failure was swallowed as "a user is signed in", so the
  SYSTEM boot agent idled forever and never contacted the backend. The probe
  now uses the supported call, logs a failure instead of hiding it, and the
  agent logs its idle/serving state so the hand-off is visible in the log.
- The installer could leave `BioUnlock.exe` and `BioUnlockProvider.dll` under
  `%ProgramFiles%` unreadable: `icacls` was asked to add inheritance entries to
  files, which stores an empty protected DACL instead, so the credential
  provider could not load at the sign-in screen. The installer now hardens the
  folder and the two files separately, and stops a running pre-login agent
  before overwriting its executable.
- Windows Fast Startup resumes a hibernated kernel and does not run at-startup
  tasks, so a shut down left the PC without a pre-login agent at all. The
  installer now disables Fast Startup and reports it as a step.

### Changed

- The PC agent is versioned `1.0.1`; the Windows download is
  `BioUnlock-1.0.1-windows-x64.exe`.

## [1.0.0] - 2026-11-01

First public release.

**Components:** Android app `1.0.0` (`versionCode` 1) · backend `0.2.1` ·
Windows agent `0.1.0`.

### Added

- Native Windows Credential Provider (C++ COM) for real logon-screen sign-in,
  registered behind a single UAC prompt by the self-installing tray app.
- Outbound-only Windows agent with a WebSocket transport, REST polling fallback,
  keepalive, and a silent-socket timeout. No inbound port is opened.
- Ed25519-signed, short-lived, single-use authorization envelopes, verified on
  the PC against a signing key pinned at pairing, with a persistent replay store.
- Flutter Android authenticator with WebAuthn passkeys, biometric approval,
  QR pairing, activity history, and a configurable self-hosted backend.
- FastAPI backend with a single-owner model, separate API and enrollment tokens,
  per-route rate limiting, Alembic migrations, and Digital Asset Links output.
- Self-installing Windows `.exe` with a setup wizard and `--silent` mode, plus
  source installers for unsigned/Smart App Control environments.
- Documentation: architecture, protocol, threat model, security notes, Windows
  authentication details, mobile build guide, and Vercel deployment guide.
- CI running the backend and agent test suites with `pytest` + `ruff`, and the
  app with `flutter analyze` + `flutter test`.

### Security

- The backend fails closed on startup when required secrets are missing outside
  development.
- The phone never uploads the passkey private key; the Windows password is stored
  with DPAPI and never transmitted.
- The prebuilt APK is bound to the reserved `biounlock.example.com` relying-party
  host and must be rebuilt with `rpHost=<your-domain>` for real passkeys.

### Known limitations

- Experimental and not independently audited. Keep another way to sign in.
- Single-owner by design: no accounts, sessions, or multi-user support.
- The Windows `.exe` is not code-signed, so Smart App Control may block it.
- `remote_unlock` stores the Windows password on the PC (DPAPI-protected) so the
  Credential Provider can sign in while no user is logged in.

[Unreleased]: https://github.com/SrijithK-Labs/BioUnlock/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/SrijithK-Labs/BioUnlock/releases/tag/v1.0.0
