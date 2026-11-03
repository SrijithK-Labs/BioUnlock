# Contributing

Thanks for considering a contribution to BioUnlock!

## Getting started

- Install prerequisites: Python 3.11+, Flutter (stable), git.
- Read `README.md` for the development quick start.
- Read `docs/architecture.md` (trust boundaries and component map), and
  `docs/protocol.md` before changing security-relevant code.

## Project conventions

- Python code: type hints everywhere, modular packages, no comments unless
  they explain "why". Run `ruff` if available (`pip install ruff`).
- Dart code: follow `flutter_lints` defaults; keep the existing layout under
  `mobile/biounlock_mobile/lib/` (`screens/`, `state/`, `services/`, `models/`,
  `widgets/`).
- Tests are required for new backend behaviour and for the PC agent. Flutter
  widget/logic tests are welcome for new screens.
- Do not hardcode backend URLs. All servers must be user-configurable.
- Do not invent cryptographic protocols. Prefer maintained libraries
  (`cryptography`, `webauthn`, platform APIs).
- Security-relevant changes get a corresponding entry in
  `docs/threat-model.md` and `docs/security.md`.

## Reporting bugs and requesting features

Use the issue forms: a bug report asks for the component, versions, and a
reproduction, and a feature request asks how the change fits the single-owner,
self-hosted design. Redact tokens, backend URLs, hostnames, and device names
from every report and screenshot. Do **not** open a public issue for a security
vulnerability — use the private advisory link in `SECURITY.md`.

## Before opening a pull request

1. Run the relevant test suites:
   - `cd server && pytest`
   - `cd pc-agent && pytest`
   - `cd mobile/biounlock_mobile && flutter analyze && flutter test`
2. Keep changes small and focused.
3. Fill in the PR description with what changed and how it was tested.
4. Never include generated binaries, `.env`, keys, or build output.

## Releasing

Maintainers: follow [`docs/releasing.md`](docs/releasing.md), which covers
version bumps, artifact builds, checksums, and the pre-publish leak checklist.

## Code of conduct

Participation is governed by `CODE_OF_CONDUCT.md`.