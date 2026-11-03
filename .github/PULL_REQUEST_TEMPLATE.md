<!--
Thanks for contributing. Keep pull requests small and focused.
Do not paste API tokens, enrollment tokens, signing keys, backend URLs,
hostnames, or device names anywhere in this description.
-->

## Summary

<!-- What problem does this change solve? Link the issue if there is one. -->

## What changed

<!-- A short list. Mention anything security-relevant explicitly. -->

-

## How it was tested

<!-- Paste the commands you actually ran and their result. Do not claim tests you did not run. -->

```bash
cd server && ruff check . && pytest
cd pc-agent && ruff check . && pytest
cd mobile/biounlock_mobile && flutter analyze && flutter test
```

## Security review

<!-- Delete lines that do not apply, but do not leave the section blank. -->

- [ ] No secrets, real hostnames, private IPs, or machine names are added.
- [ ] Pairing, envelope verification, secret storage, and the Credential Provider
      are unchanged, or the change is explained above and in `docs/threat-model.md`.
- [ ] The change does not add an inbound port, telemetry, or a hosted dependency.
- [ ] New behaviour has tests, or the reason it cannot be tested is stated above.

## Checklist

- [ ] I read `CONTRIBUTING.md` and `SECURITY.md`.
- [ ] I updated documentation or `CHANGELOG.md` where behaviour changed.
- [ ] I did not commit generated binaries, `.env` files, keys, or build output.
