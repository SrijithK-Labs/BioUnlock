import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import '../models/account.dart';
import '../models/misc.dart';
import '../services/api_client.dart';
import '../services/api_exception.dart';
import '../services/passkey_service.dart';
import '../services/session_store.dart';

/// Root application state: server configuration, session, and the shared
/// [ApiClient]. Child controllers read [api] from here.
class AppState extends ChangeNotifier {
  AppState({
    required this.store,
    required PasskeyService passkeyService,
    http.Client? httpClient,
  }) : _passkeyService = passkeyService,
       _httpClient = httpClient;

  final SessionStore store;
  final PasskeyService _passkeyService;
  final http.Client? _httpClient;

  ApiClient? _api;
  Session? _session;
  ServerInfo? _serverInfo;
  bool _busy = false;
  String? _error;
  bool _initialized = false;

  ApiClient? get api => _api;
  PasskeyService get passkeys => _passkeyService;
  Session? get session => _session;
  ServerInfo? get serverInfo => _serverInfo;
  String? get serverUrl => _serverInfo != null ? _api?.baseUrl : null;
  bool get isConfigured => _api != null;
  bool get isAuthenticated => _session != null;
  bool get busy => _busy;
  String? get error => _error;
  bool get initialized => _initialized;

  void _setBusy(bool value) {
    _busy = value;
    notifyListeners();
  }

  void _setError(String? value) {
    _error = value;
    notifyListeners();
  }

  /// Loads any stored configuration and session on startup.
  Future<void> init() async {
    final url = await store.readServerUrl();
    if (url != null && url.isNotEmpty) {
      _api = ApiClient(baseUrl: url, httpClient: _httpClient);
    }
    final stored = await store.readSession();
    if (stored != null && !stored.isExpired && _api != null) {
      _api!.token = stored.token;
      _session = stored;
      // Validate the session and refresh server info in the background.
      try {
        await _api!.me();
        _serverInfo = await _api!.serverInfo();
      } on ApiException {
        await _clearSession();
      }
    }
    _initialized = true;
    notifyListeners();
  }

  /// Points the app at a (new) server and validates reachability.
  Future<bool> configureServer(String url) async {
    final normalized = _normalizeUrl(url);
    if (normalized == null) {
      _setError('Enter a valid server URL, e.g. https://biounlock.example.com');
      return false;
    }
    _setBusy(true);
    _setError(null);
    try {
      final client = ApiClient(baseUrl: normalized, httpClient: _httpClient);
      final info = await client.serverInfo();
      _api = client;
      _serverInfo = info;
      await store.writeServerUrl(normalized);
      return true;
    } on ApiException catch (error) {
      _setError(error.message);
      return false;
    } finally {
      _setBusy(false);
    }
  }

  Future<bool> register(String email, String password) async {
    final client = _api;
    if (client == null) return false;
    _setBusy(true);
    _setError(null);
    try {
      final session = await client.register(email, password);
      await _applySession(session);
      return true;
    } on ApiException catch (error) {
      _setError(error.message);
      return false;
    } finally {
      _setBusy(false);
    }
  }

  Future<bool> login(String email, String password) async {
    final client = _api;
    if (client == null) return false;
    _setBusy(true);
    _setError(null);
    try {
      final session = await client.login(email, password);
      await _applySession(session);
      return true;
    } on ApiException catch (error) {
      _setError(error.message);
      return false;
    } finally {
      _setBusy(false);
    }
  }

  Future<void> _applySession(Session session) async {
    _api!.token = session.token;
    _session = session;
    await store.writeSession(session);
    notifyListeners();
  }

  Future<void> logout() async {    try {
      await _api?.logout();
    } on ApiException {
      // Best effort; local session is cleared regardless.
    }
    await _clearSession();
  }

  Future<void> _clearSession() async {
    _api?.token = null;
    _session = null;
    await store.clearSession();
    notifyListeners();
  }

  /// Forgets the server URL and session, returning to first-run setup.
  Future<void> resetServer() async {
    await _clearSession();
    await store.writeServerUrl('');
    _api = null;
    _serverInfo = null;
    notifyListeners();
  }

  static String? _normalizeUrl(String input) {
    var value = input.trim();
    if (value.isEmpty) return null;
    if (!value.startsWith('http://') && !value.startsWith('https://')) {
      value = 'https://$value';
    }
    final uri = Uri.tryParse(value);
    if (uri == null || uri.host.isEmpty) return null;
    return value.endsWith('/') ? value.substring(0, value.length - 1) : value;
  }

  static String get defaultServerUrl => AppConfig.defaultServerUrl;
}
