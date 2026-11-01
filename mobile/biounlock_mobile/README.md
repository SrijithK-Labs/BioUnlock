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

1. Download `BioUnlock-1.0.0-android.apk` from
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
flutter build apk --release    # requires android/key.properties and a private keystore
```

From `mobile/biounlock_mobile/android`, create an upload keystore. `keytool`
prompts for passwords; do not put them on the command line:

```powershell
keytool -genkeypair -v -keystore app\upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

Create the ignored `android/key.properties` file:

```properties
storeFile=app/upload-keystore.jks
storePassword=<your-keystore-password>
keyAlias=upload
keyPassword=<your-key-password>
```

Never commit either file or share the private key. Use the same signing identity
for updates; changing it breaks Android app association and may require passkey
re-registration. Configure Digital Asset Links with the release signing
certificate fingerprint, not the debug certificate.

The backend serves the fingerprint bundled in `server/app/static_assets.py`
(`ANDROID_SHA256_FINGERPRINTS`), which is the project's release certificate. If
you sign with your own keystore, add your certificate's SHA-256 there too —
otherwise Android refuses to create passkeys for your APK.

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
3. Have `BIO_RP_ID` pinned to that domain. (Development may use `auto`, which
   follows the request host; deployed servers refuse it.)

Because of this, passkey login cannot be tested against a bare `localhost` RP on
a physical device. See [`../../docs/mobile.md`](../../docs/mobile.md) for the
full requirement, build steps, and Android/Gradle troubleshooting (IPv6, Kotlin
incremental caches, corrupted Gradle caches).

## Project structure

```
lib/
  main.dart, app.dart, config.dart   App entry, root gate, constants
  models/                            Device, AuthRequest, misc value types
  services/                          ApiClient, token/URL stores, PasskeyService
  state/                             AppState + devices/passkeys/requests controllers
  screens/                           Setup, Auth, Home (4 tabs), scan, device detail
android/                             Manifest (INTERNET, CAMERA), Gradle config
test/                                Unit + widget tests with fakes/mocks
```

Requires Flutter 3.47+ (Dart 3.13+). Configuration (server URL, API token, and
the optional enrollment token) is stored with `flutter_secure_storage`. The first
passkey is added with the API token alone; after that, `BIO_ENROLLMENT_TOKEN`
must also be entered under **Settings → Enrollment token** to add or remove
passkeys.

## Tests

```bash
flutter analyze
flutter test
```

## Security

The phone sends `Authorization: Bearer <token>` on every owner call; the passkey
private key stays in platform-secure storage and is never uploaded. See
[`../../docs/security.md`](../../docs/security.md).
