import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../models/misc.dart';
import '../services/api_client.dart';
import '../services/api_exception.dart';
import '../services/api_token_store.dart';
import '../services/enrollment_token_store.dart';
import '../services/passkey_service.dart';
import '../services/preferences_store.dart';
import '../services/server_url_store.dart';

/// Root application state: server configuration, theme and the shared
/// [ApiClient]. Child controllers read [api] from here.
class AppState extends ChangeNotifier {
  AppState({
    required this.store,
    required PasskeyService passkeyService,
    ApiTokenStore? tokenStore,
    EnrollmentTokenStore? enrollmentTokenStore,
    PreferencesStore? preferences,
    http.Client? httpClient,
  }) : _passkeyService = passkeyService,
       _tokenStore = tokenStore ?? InMemoryApiTokenStore(),
       _enrollmentTokenStore =
           enrollmentTokenStore ?? InMemoryEnrollmentTokenStore(),
       _preferences = preferences ?? InMemoryPreferencesStore(),
       _httpClient = httpClient;

  final ServerUrlStore store;
  final PasskeyService _passkeyService;
  final ApiTokenStore _tokenStore;
  final EnrollmentTokenStore _enrollmentTokenStore;
  final PreferencesStore _preferences;
  final http.Client? _httpClient;

  ApiClient? _api;
  ServerInfo? _serverInfo;
  String? _apiToken;
  String? _enrollmentToken;
  bool _busy = false;
  String? _error;
  bool _initialized = false;
  ThemeMode _themeMode = ThemeMode.system;

  ApiClient? get api => _api;
  PasskeyService get passkeys => _passkeyService;
  ServerInfo? get serverInfo => _serverInfo;
  String? get serverUrl => _api?.baseUrl;
  String? get apiToken => _apiToken;
  String? get enrollmentToken => _enrollmentToken;
  bool get isConfigured => _api != null;
  bool get busy => _busy;
  String? get error => _error;
  bool get initialized => _initialized;
  ThemeMode get themeMode => _themeMode;

  void _setBusy(bool value) {
    _busy = value;
    notifyListeners();
  }

  void _setError(String? value) {
    _error = value;
    notifyListeners();
  }

  /// Loads any stored server URL and theme mode on startup and refreshes
  /// server info in the background. A server that is unreachable at launch
  /// stays configured so the user can fix the URL from Settings.
  Future<void> init() async {
    _themeMode = _themeModeFromName(await _preferences.readThemeMode());
    _apiToken = _cleanToken(await _tokenStore.readToken());
    _enrollmentToken = _cleanToken(await _enrollmentTokenStore.readToken());
    final url = await store.readServerUrl();
    if (url != null && url.isNotEmpty) {
      final normalized = _normalizeUrl(url);
      if (normalized != null) {
        _api = ApiClient(
          baseUrl: normalized,
          apiToken: _apiToken,
          enrollmentToken: _enrollmentToken,
          httpClient: _httpClient,
        );
        try {
          _serverInfo = await _api!.serverInfo();
        } on ApiException {
          // Best effort; the app remains usable with the stored URL.
        }
      }
    }
    _initialized = true;
    notifyListeners();
  }

  /// Updates and persists the app-wide [ThemeMode].
  Future<void> setThemeMode(ThemeMode mode) async {
    if (mode == _themeMode) return;
    _themeMode = mode;
    notifyListeners();
    await _preferences.writeThemeMode(_themeModeName(mode));
  }

  /// Points the app at a (new) server and validates reachability. When
  /// [token] is supplied it replaces the stored API token; otherwise the
  /// existing token is reused.
  Future<bool> configureServer(String url, {String? token}) async {
    final normalized = _normalizeUrl(url);
    if (normalized == null) {
      _setError('Enter a valid server URL, e.g. https://biounlock.example.com');
      return false;
    }
    final effectiveToken = token == null ? _apiToken : _cleanToken(token);
    _setBusy(true);
    _setError(null);
    try {
      final client = ApiClient(
        baseUrl: normalized,
        apiToken: effectiveToken,
        enrollmentToken: _enrollmentToken,
        httpClient: _httpClient,
      );
      final info = await client.serverInfo();
      _api = client;
      _serverInfo = info;
      _apiToken = effectiveToken;
      await store.writeServerUrl(normalized);
      await _tokenStore.writeToken(effectiveToken ?? '');
      return true;
    } on ApiException catch (error) {
      _setError(error.message);
      return false;
    } finally {
      _setBusy(false);
    }
  }

  /// Updates and persists the enrollment token used to add or remove passkeys
  /// after the first one. An empty value clears it.
  Future<void> setEnrollmentToken(String? value) async {
    final cleaned = _cleanToken(value);
    _enrollmentToken = cleaned;
    await _enrollmentTokenStore.writeToken(cleaned ?? '');
    if (_api != null) {
      _api = ApiClient(
        baseUrl: _api!.baseUrl,
        apiToken: _apiToken,
        enrollmentToken: cleaned,
        httpClient: _httpClient,
      );
    }
    notifyListeners();
  }

  /// Forgets the configured server URL and API tokens, returning to first-run
  /// setup.
  Future<void> resetServer() async {
    await store.writeServerUrl('');
    await _tokenStore.writeToken('');
    await _enrollmentTokenStore.writeToken('');
    _api = null;
    _serverInfo = null;
    _apiToken = null;
    _enrollmentToken = null;
    notifyListeners();
  }

  static String? _cleanToken(String? value) {
    final trimmed = value?.trim();
    return (trimmed == null || trimmed.isEmpty) ? null : trimmed;
  }

  static String? _normalizeUrl(String input) {
    var value = input.trim();
    if (value.isEmpty) return null;
    if (!value.startsWith('http://') && !value.startsWith('https://')) {
      value = 'https://$value';
    }
    final uri = Uri.tryParse(value);
    if (uri == null ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.scheme != 'https' && uri.scheme != 'http')) {
      return null;
    }
    if (uri.scheme == 'http' && !_allowsCleartextHost(uri.host)) return null;
    return value.endsWith('/') ? value.substring(0, value.length - 1) : value;
  }

  static bool _allowsCleartextHost(String host) {
    if (kReleaseMode) return false;
    final normalizedHost = host.toLowerCase();
    if (normalizedHost == 'localhost' || normalizedHost.endsWith('.localhost')) {
      return true;
    }
    final address = InternetAddress.tryParse(normalizedHost);
    if (address == null || address.type != InternetAddressType.IPv4) return false;
    final octets = address.rawAddress;
    return octets[0] == 10 ||
        (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) ||
        (octets[0] == 192 && octets[1] == 168);
  }

  static String _themeModeName(ThemeMode mode) => switch (mode) {
    ThemeMode.light => 'light',
    ThemeMode.dark => 'dark',
    ThemeMode.system => 'system',
  };

  static ThemeMode _themeModeFromName(String? name) => switch (name) {
    'light' => ThemeMode.light,
    'dark' => ThemeMode.dark,
    _ => ThemeMode.system,
  };
}