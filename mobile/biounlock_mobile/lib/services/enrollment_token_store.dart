import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persists the enrollment token required to change passkeys once one exists.
abstract class EnrollmentTokenStore {
  Future<String?> readToken();
  Future<void> writeToken(String token);
}

/// Secure-storage backed implementation used on real devices.
class SecureEnrollmentTokenStore implements EnrollmentTokenStore {
  SecureEnrollmentTokenStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _tokenKey = 'biounlock.enrollment_token';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readToken() => _storage.read(key: _tokenKey);

  @override
  Future<void> writeToken(String token) =>
      _storage.write(key: _tokenKey, value: token);
}

/// In-memory store for tests and for platforms without secure storage.
class InMemoryEnrollmentTokenStore implements EnrollmentTokenStore {
  InMemoryEnrollmentTokenStore({String? token}) : _token = token;

  String? _token;

  @override
  Future<String?> readToken() async => _token;

  @override
  Future<void> writeToken(String token) async => _token = token;
}
