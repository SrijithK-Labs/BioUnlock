# BioUnlock mobile app

<p align="center">
  <img src="../../logo/logo.png" alt="BioUnlock logo" width="110" />
</p>

Flutter Android authenticator: approve Windows PC unlock/lock requests with your
phone's biometric-backed passkey. It never stores a Windows password and never
claims an unlock that didn't happen.

The app is generic — it is not tied to any server. You enter your backend
**URL** and **API token** at runtime, so one APK works for any deployment.

## Install

1. Download `app-release.apk` from
   [Releases](https://github.com/SrijithK-Labs/BioUnlock/releases) and install it
   (allow install from your browser/files app when prompted).
2. Open the app, go to **Settings → Server**, and enter your backend base URL
   (your hosted backend, e.g. `https://unlock.example.com`). Tap **Test
   Connection**.
3. Enter the same **API token** your backend uses. Then register a passkey when
   prompted.

Real passkeys require an **HTTPS** relying-party domain with a Digital Asset
Links association — see [Passkey requirement](#passkey-requirement) below.

## Build and run

```bash
cd mobile/biounlock_mobile
flutter pub get
flutter analyze
flutter test
flutter run                    # debug on a connected device
flutter build apk --debug      # debug APK
flutter build apk --release    # signed release APK (needs a signing config)
```

Output APKs land in `build/app/outputs/flutter-apk/` (`app-debug.apk` or
`app-release.apk`). Attach the release APK to a GitHub Release to distribute it.
A physical Android 7.0 (API 24)+ device is required to exercise real passkeys —
emulators have no hardware authenticator.

## Passkey requirement

The backend is the WebAuthn relying party. For Android passkeys to work against
a real server it must:

1. Serve the backend over **HTTPS** on the RP domain.
2. Publish Digital Asset Links at
   `https://<your-domain>/.well-known/assetlinks.json` containing the app package
   (`com.biounlock.biounlock_mobile`) and the SHA-256 of the APK's signing
   certificate.
3. Have `BIO_RP_ID` match that domain (the default `auto` derives it from the
   request host, so no configuration is usually needed).

Because of this, passkey login cannot be tested against a bare `localhost` RP on
a physical device. See [`../../docs/mobile.md`](../../docs/mobile.md) for the
full requirement, build steps, and Android/Gradle troubleshooting (IPv6, Kotlin
incremental caches, corrupted Gradle caches).

## Project structure

```
lib/
  main.dart, app.dart, config.dart   App entry, root gate, constants
  models/                            Account, Device, AuthRequest, value types
  services/                          ApiClient, SessionStore, PasskeyService
  state/                             AppState + devices/passkeys/requests controllers
  screens/                           Setup, Auth, Home (4 tabs), scan, device detail
android/                             Manifest (INTERNET, CAMERA), Gradle config
test/                                Unit + widget tests with fakes/mocks
```

Requires Flutter 3.47+ (Dart 3.13+). Configuration (server URL and API token) is
stored with `flutter_secure_storage`.

## Tests

```bash
flutter analyze
flutter test
```

## Security

The phone sends `Authorization: Bearer <token>` on every owner call; the passkey
private key stays in platform-secure storage and is never uploaded. See
[`../../docs/security.md`](../../docs/security.md).
