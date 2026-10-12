import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persists small app preferences (currently just the chosen theme mode).
abstract class PreferencesStore {
  Future<String?> readThemeMode();
  Future<void> writeThemeMode(String value);
}

/// Secure-storage backed implementation used on real devices.
class SecurePreferencesStore implements PreferencesStore {
  SecurePreferencesStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _themeModeKey = 'biounlock.theme_mode';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readThemeMode() => _storage.read(key: _themeModeKey);

  @override
  Future<void> writeThemeMode(String value) =>
      _storage.write(key: _themeModeKey, value: value);
}

/// In-memory store for tests.
class InMemoryPreferencesStore implements PreferencesStore {
  InMemoryPreferencesStore({String? themeMode}) : _themeMode = themeMode;

  String? _themeMode;

  @override
  Future<String?> readThemeMode() async => _themeMode;

  @override
  Future<void> writeThemeMode(String value) async => _themeMode = value;
}
