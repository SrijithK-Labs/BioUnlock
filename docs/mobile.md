# Mobile app (Flutter / Android)

The BioUnlock mobile app pairs an Android phone with a Windows PC and authorizes
requests using the phone's biometric-backed passkey. It never stores a Windows
password and never claims an unlock that did not happen.

## Prerequisites

- Flutter 3.47+ (Dart 3.13+) with the Android toolchain (`flutter doctor`).
- Android SDK with a device/emulator on Android 7.0 (API 24)+. The Gradle config
  pins `minSdk` to at least 23 (`android/app/build.gradle.kts`).
- A **physical device** is required to exercise real passkeys. Emulators do not
  have a hardware-backed authenticator.

## Configuration

The app never hardcodes a backend. The user enters the backend base URL in
**Settings → Server** and taps **Test Connection**. Development hosts
(`localhost`, loopback, and private LAN ranges) may use `http://`; any other
host must be `https://`. The URL, owner API token, and optional enrollment token
are stored with `flutter_secure_storage`. The first passkey can be registered
with the API token alone; afterwards, changing passkeys requires the enrollment
token under **Settings → Enrollment token**.

From the Android emulator, the host machine is reachable at `http://10.0.2.2:8000`.

## Passkey / relying-party requirement

The backend acts as the WebAuthn relying party (RP). For Android passkeys to work
against a real server you must:

1. Serve the backend over **HTTPS** on the RP domain (e.g. `unlock.example.com`).
2. Publish a **Digital Asset Links** file at
   `https://unlock.example.com/.well-known/assetlinks.json` containing the app's
   package name (`com.biounlock.biounlock_mobile`) and the SHA-256 of the signing
   certificate.
3. Ensure the backend `BIO_WEBAUTHN_RP_ID` matches that domain.

Without the asset-links association, the OS refuses to create/use credentials for
the domain. This means passkey **login cannot be tested against a bare
`localhost` RP on a physical device** — use a reachable HTTPS domain with the
association in place, or a development tunnel with matching RP ID.

## Build & run

```bash
cd mobile/biounlock_mobile
flutter pub get
flutter analyze
flutter test
flutter run                 # debug on a connected device
flutter build apk --debug    # debug APK
flutter build apk --release  # release APK (requires signing config)
```

The debug APK is written to `build/app/outputs/flutter-apk/app-debug.apk`.

## Android / Gradle troubleshooting

These are environment issues, not app bugs:

- **`java.net.ConnectException: Connection timed out` while Gradle resolves
  dependencies.** The JVM may prefer an IPv6 (AAAA) route that is unreachable.
  Force IPv4 for the build:

  ```powershell
  $env:JAVA_TOOL_OPTIONS="-Djava.net.preferIPv4Stack=true"
  flutter build apk --debug
  ```

- **`Could not close incremental caches ...` during Kotlin compilation.** A
  known Windows issue. The app disables Kotlin incremental compilation and the
  Gradle build cache in `android/gradle.properties`
  (`kotlin.incremental=false`, `org.gradle.caching=false`).

- **`Could not find EOCD ...` or zip errors from the Gradle cache.** Caused by
  truncated artifacts from an interrupted download. Purge and re-download:

  ```powershell
  .\android\gradlew.bat --stop
  Remove-Item -Recurse -Force "$env:USERPROFILE\.gradle\caches\modules-2"
  flutter clean
  flutter build apk --debug
  ```

The Gradle wrapper uses the `-bin` distribution (`gradle-9.3.1-bin.zip`) to keep
the download smaller; that is set in
`android/gradle/wrapper/gradle-wrapper.properties`.

## Project structure

```
lib/
  main.dart, app.dart, config.dart   App entry, root gate, constants
  models/                            Account, Device, AuthRequest, misc value types
  services/                          ApiClient, SessionStore, PasskeyService
  state/                             AppState + devices/passkeys/requests controllers
  screens/                           Setup, Auth, Home (4 tabs), scan, device detail
test/                                Unit + widget tests with fakes/mocks
android/                             Manifest (INTERNET, CAMERA), Gradle config
```

State management uses `provider`. HomeScreen-level controllers live below the
root `Navigator`, so pushed routes (e.g. `DeviceDetailScreen`) receive their
controller via constructor arguments.

## Tests

`flutter test` covers models, the API client, `AppState`, and the authorization
flow with a fake passkey service and a routed mock HTTP client. Run
`flutter analyze` for static checks.
