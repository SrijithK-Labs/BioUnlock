import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/misc.dart';
import '../services/api_client.dart';
import '../services/api_exception.dart';
import '../services/passkey_service.dart';
import '../services/server_url_store.dart';

/// Root application state: server configuration and the shared [ApiClient].
/// Child controllers read [api] from here.
class AppState extends ChangeNotifier {
  AppState({
    required this.store,
    required PasskeyService passkeyService,
    http.Client? httpClient,
  }) : _passkeyService = passkeyService,
       _httpClient = httpClient;

  final ServerUrlStore store;
  final PasskeyService _passkeyService;
  final http.Client? _httpClient;

  ApiClient? _api;
  ServerInfo? _serverInfo;
  bool _busy = false;
  String? _error;
  bool _initialized = false;

  ApiClient? get api => _api;
  PasskeyService get passkeys => _passkeyService;
  ServerInfo? get serverInfo => _serverInfo;
  String? get serverUrl => _api?.baseUrl;
  bool get isConfigured => _api != null;
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

  /// Loads any stored server URL on startup and refreshes server info in the
  /// background. A server that is unreachable at launch stays configured so
  /// the user can fix the URL from Settings.
  Future<void> init() async {
    final url = await store.readServerUrl();
    if (url != null && url.isNotEmpty) {
      _api = ApiClient(baseUrl: url, httpClient: _httpClient);
      try {
        _serverInfo = await _api!.serverInfo();
      } on ApiException {
        // Best effort; the app remains usable with the stored URL.
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

  /// Forgets the configured server URL, returning to first-run setup.
  Future<void> resetServer() async {
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
}