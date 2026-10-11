import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/account.dart';

/// Persists the server base URL and the current session token.
abstract class SessionStore {
  Future<String?> readServerUrl();
  Future<void> writeServerUrl(String url);

  Future<Session?> readSession();
  Future<void> writeSession(Session session);
  Future<void> clearSession();
}

/// Secure-storage backed implementation used on real devices.
class SecureSessionStore implements SessionStore {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _serverUrlKey = 'biounlock.server_url';
  static const _sessionKey = 'biounlock.session';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readServerUrl() => _storage.read(key: _serverUrlKey);

  @override
  Future<void> writeServerUrl(String url) =>
      _storage.write(key: _serverUrlKey, value: url);

  @override
  Future<Session?> readSession() async {
    final raw = await _storage.read(key: _sessionKey);
    if (raw == null) return null;
    try {
      return Session.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      await clearSession();
      return null;
    }
  }

  @override
  Future<void> writeSession(Session session) =>
      _storage.write(key: _sessionKey, value: jsonEncode(session.toJson()));

  @override
  Future<void> clearSession() => _storage.delete(key: _sessionKey);
}

/// In-memory store for tests and for platforms without secure storage.
class InMemorySessionStore implements SessionStore {
  InMemorySessionStore({String? serverUrl, Session? session})
    : _serverUrl = serverUrl,
      _session = session;

  String? _serverUrl;
  Session? _session;

  @override
  Future<String?> readServerUrl() async => _serverUrl;

  @override
  Future<void> writeServerUrl(String url) async => _serverUrl = url;

  @override
  Future<Session?> readSession() async => _session;

  @override
  Future<void> writeSession(Session session) async => _session = session;

  @override
  Future<void> clearSession() async => _session = null;
}
