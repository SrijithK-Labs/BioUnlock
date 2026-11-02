/// Build-time and user-configurable constants.
///
/// The server URL is intentionally *not* hardcoded to a production host: each
/// deployment is self-hosted, so the user must supply their own HTTPS base URL.
class AppConfig {
  const AppConfig._();

  /// Optional compile-time default base URL, e.g.
  /// `flutter run --dart-define=BIOUNLOCK_DEFAULT_SERVER_URL=https://...`.
  static const String defaultServerUrl =
      String.fromEnvironment('BIOUNLOCK_DEFAULT_SERVER_URL', defaultValue: '');

  static const String appName = 'BioUnlock';
  static const String pairingType = 'biounlock-pairing';
  static const int pairingPayloadVersion = 1;

  /// How often the app polls a request's status while authorizing.
  static const Duration statusPollInterval = Duration(seconds: 2);
  static const Duration statusPollTimeout = Duration(seconds: 90);
}
