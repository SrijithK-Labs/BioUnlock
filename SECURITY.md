# Security Policy

BioUnlock is an **experimental** authentication project. Please do not rely on
it to protect systems where loss or compromise of the primary Windows
credentials is unacceptable.

## Supported versions

Only the latest commit on the default branch is supported. There are no
tagged releases yet.

## Reporting a vulnerability

Please report security issues privately — never in a public issue.

1. Send an email to the maintainers (see the git history / repository owners).
2. Include:
   - A description of the issue and its impact.
   - Affected component(s) and version/commit.
   - A minimal reproduction, if possible.
   - Any suggested remediation, if you have one.
3. Do not share the details publicly until maintainers have acknowledged and
   addressed the report.

Maintainers aim to acknowledge reports within 7 days and to provide an
assessment and remediation timeline.

## Security expectations

- Never commit `.env`, private keys, certificates, or production credentials.
- Only HTTPS should be used to talk to production BioUnlock backends.
- The backend never sees your Windows password. BioUnlock does not implement
  Windows logon bypass.
- Phone biometrics are handled by the platform (`local_auth` /
  WebAuthn passkeys). BioUnlock never collects, stores, or transmits raw
  biometric data.