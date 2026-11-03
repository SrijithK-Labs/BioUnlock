# Release runbook

How to cut a BioUnlock release. Replace `X.Y.Z` with the release version and
`<domain>` with your own relying-party domain.

## Before you start

- Work from a clean `master` checkout: `git status` must be empty and
  `git pull --ff-only` must succeed.
- CI must be green on the commit you are tagging.
- You need the Android upload keystore and its passwords, plus a Windows machine
  with the Visual Studio C++ toolchain for the Credential Provider.
- Never commit `android/key.properties`, the keystore, `.env` files, or any
  generated secret. They are already ignored; keep it that way.

## 1. Bump versions

Update every location that carries a version. They intentionally move
independently, so bump only the components that changed.

| Component | File | Field |
| --- | --- | --- |
| Android app | `mobile/biounlock_mobile/pubspec.yaml` | `version: X.Y.Z+N` (`N` is `versionCode`, always increase it) |
| Backend | `server/pyproject.toml` | `[project] version` |
| Backend | `server/app/__init__.py` | `__version__` |
| Windows agent | `pc-agent/biounlock_agent/__init__.py` | `__version__` |

Then update `CHANGELOG.md`: move items out of `[Unreleased]`, add the release
date, and add the compare/release links at the bottom.

## 2. Run the full suite

```bash
cd server && ruff check . && pytest
cd pc-agent && ruff check . && pytest
cd mobile/biounlock_mobile && flutter analyze && flutter test
```

Do not tag until all three pass locally and CI is green.

## 3. Build the Windows agent

On Windows, from `pc-agent`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File build.ps1 -Clean
```

`build.ps1` builds the Credential Provider when the C++ toolchain is available
and then runs PyInstaller. The output is `dist\BioUnlock.exe` (no console
window). If the Credential Provider DLL is missing, the build warns and produces
an `.exe` without logon-screen unlock; do not ship that as a full release.

Rename the artifact into a staging folder **outside** the repository, so release
binaries can never be committed by accident:

```powershell
$out = Join-Path $env:TEMP "biounlock-release"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Copy-Item dist\BioUnlock.exe (Join-Path $out "BioUnlock-X.Y.Z-windows-x64.exe")
```

The executable is **not code-signed**. Say so in the release notes; do not imply
otherwise.

## 4. Build the Android APK

Create the ignored signing file at
`mobile/biounlock_mobile/android/key.properties`:

```properties
storeFile=app/upload-keystore.jks
storePassword=<your-keystore-password>
keyAlias=upload
keyPassword=<your-key-password>
rpHost=<domain>
```

`rpHost` must equal the backend's `BIO_RP_ID` and the host that serves
`/.well-known/assetlinks.json`. A mismatch silently breaks passkeys.

```bash
cd mobile/biounlock_mobile
flutter clean
flutter pub get
flutter build apk --release
```

Output: `build/app/outputs/flutter-apk/app-release.apk`. Copy it to the same
staging folder as `BioUnlock-X.Y.Z-android.apk` (rerun the `$out = ...` line from
step 3 if you opened a new PowerShell session):

```powershell
Copy-Item build\app\outputs\flutter-apk\app-release.apk `
  (Join-Path $out "BioUnlock-X.Y.Z-android.apk")
```

Verify the signature before publishing:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\build-tools\<version>\apksigner.bat" verify --print-certs `
  build\app\outputs\flutter-apk\app-release.apk
```

The reported SHA-256 must match the fingerprint served by the backend's
`ANDROID_SHA256_FINGERPRINTS`. If you sign with a different keystore, update
`server/app/static_assets.py` first, or Android will refuse to create passkeys
for the new APK.

## 5. Record checksums

```powershell
Get-FileHash -Algorithm SHA256 (Join-Path $out "BioUnlock-X.Y.Z-windows-x64.exe")
Get-FileHash -Algorithm SHA256 (Join-Path $out "BioUnlock-X.Y.Z-android.apk")
```

Put both hashes in the release notes. They are the only way for a downloader to
confirm the bytes they received.

## 6. Tag and publish

```bash
git status --short          # review: source changes only, no binaries
git add -A
git commit -m "Release vX.Y.Z"
git push origin master

git tag -a vX.Y.Z -m "BioUnlock vX.Y.Z"
git push origin vX.Y.Z
```

The artifacts live in `$env:TEMP\biounlock-release`, outside the working tree,
so `git add -A` cannot stage them.

Create the GitHub release for that tag and attach both artifacts from that
folder. The release body should cover:

- component versions and the supported platforms;
- the two SHA-256 hashes;
- a short "what changed" section from `CHANGELOG.md`;
- the honest caveats: experimental, unaudited, single-owner, unsigned `.exe`,
  and the `rpHost` rebuild requirement for real passkeys;
- a link to `SECURITY.md` for private vulnerability reports.

## 7. Verify the published release

1. Open the release page while signed out and download both assets.
2. Confirm each downloaded file's SHA-256 matches the published value.
3. Confirm CI is green for the tagged commit and the badge shows the new tag.
4. Confirm the release does not mention internal hosts, tokens, tunnel URLs,
   machine names, or deployment identifiers.

## Leak checklist

Run this against the tagged tree, not just the working copy:

```bash
git grep -n -I -E "trycloudflare|ngrok|BIO_SIGNING_KEY=\"?-----BEGIN"
git ls-files | Select-String -Pattern "key\.properties|\.jks|\.keystore|\.env$|device_key|windows_credential"
```

The second command must return nothing. The first must return no real values;
placeholder examples in `.env.example` and `server/README.md` are expected, and
so are the synthetic `192.168.1.10` / `10.0.2.2` addresses used in UI hints and
tests. Review every remaining hit by hand, and search separately for your own
machine name and domain (do not add them to this public checklist).

Also check new screenshots for visible hostnames, device names, account names,
and notification previews; redact before committing. Do not rely on image
metadata being stripped.

## If something is wrong

- **Bad artifact, same version:** fix the source, bump the patch version, and
  publish a new tag. Replacing an asset in place changes the bytes behind an
  unchanged URL and invalidates the published checksum.
- **Leaked secret:** rotate it on the backend first, then remove it from the
  repository and from the release assets. Treat the old value as compromised.
- **Broken passkeys after a release:** confirm `rpHost`, `BIO_RP_ID`, and the
  asset-links fingerprint all match the signing certificate. Changing `BIO_RP_ID`
  invalidates every existing passkey.
