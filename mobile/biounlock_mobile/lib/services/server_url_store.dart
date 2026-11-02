import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persists the backend base URL configured at setup time.
abstract class ServerUrlStore {
  Future<String?> readServerUrl();
  Future<void> writeServerUrl(String url);
}

/// Secure-storage backed implementation used on real devices.
class SecureServerUrlStore implements ServerUrlStore {
  SecureServerUrlStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _serverUrlKey = 'biounlock.server_url';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readServerUrl() => _storage.read(key: _serverUrlKey);

  @override
  Future<void> writeServerUrl(String url) =>
      _storage.write(key: _serverUrlKey, value: url);
}

/// In-memory store for tests and for platforms without secure storage.
class InMemoryServerUrlStore implements ServerUrlStore {
  InMemoryServerUrlStore({String? serverUrl}) : _serverUrl = serverUrl;

  String? _serverUrl;

  @override
  Future<String?> readServerUrl() async => _serverUrl;

  @override
  Future<void> writeServerUrl(String url) async => _serverUrl = url;
}