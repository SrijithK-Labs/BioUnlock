import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/account.dart';
import '../models/auth_request.dart';
import '../models/device.dart';
import '../models/misc.dart';
import 'api_exception.dart';

/// Thin, typed wrapper around the BioUnlock REST API.
///
/// The base URL is supplied by the user at setup time (each deployment is
/// self-hosted) and never hardcoded.
class ApiClient {
  ApiClient({required this.baseUrl, http.Client? httpClient})
    : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  /// The bearer token used for account-scoped endpoints.
  String? token;

  Uri _uri(String path) {
    final normalized = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    return Uri.parse('$normalized/api/v1$path');
  }

  Map<String, String> _headers({Map<String, String>? extra}) {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    };
    if (token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    if (extra != null) {
      headers.addAll(extra);
    }
    return headers;
  }

  Future<dynamic> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) async {
    final request = http.Request(method, _uri(path))
      ..headers.addAll(_headers(extra: headers));
    if (body != null) {
      request.body = jsonEncode(body);
    }
    final http.StreamedResponse streamed;
    try {
      streamed = await _http.send(request);
    } on Exception catch (error) {
      throw ApiException(0, 'network_error', 'Cannot reach the server: $error');
    }
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return null;
      return jsonDecode(response.body);
    }
    throw ApiException.fromBody(response.statusCode, response.body);
  }

  Future<T> _get<T>(String path, T Function(dynamic) decode) async =>
      decode(await _send('GET', path));

  // --- Server info ---

  Future<ServerInfo> serverInfo() =>
      _get('/server/info', (d) => ServerInfo.fromJson(d as Map<String, dynamic>));

  // --- Accounts ---

  Future<Session> register(String email, String password) async => Session.fromJson(
    await _send('POST', '/auth/register', body: {
      'email': email,
      'password': password,
    }) as Map<String, dynamic>,
  );

  Future<Session> login(String email, String password) async => Session.fromJson(
    await _send('POST', '/auth/login', body: {
      'email': email,
      'password': password,
    }) as Map<String, dynamic>,
  );

  Future<void> logout() => _send('POST', '/auth/logout');

  Future<Account> me() async =>
      Account.fromJson(await _send('GET', '/auth/me') as Map<String, dynamic>);

  Future<List<SecurityEvent>> securityEvents({int limit = 50}) async {
    final data = await _send('GET', '/security-events?limit=$limit');
    return (data as List)
        .map((e) => SecurityEvent.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // --- WebAuthn / passkeys ---

  Future<Map<String, dynamic>> passkeyRegisterBegin() async =>
      await _send('POST', '/webauthn/register/begin') as Map<String, dynamic>;

  Future<PasskeyCredential> passkeyRegisterComplete({
    required String challengeId,
    required Map<String, dynamic> credential,
    String? name,
  }) async => PasskeyCredential.fromJson(
    await _send('POST', '/webauthn/register/complete', body: {
      'challenge_id': challengeId,
      'credential': credential,
      'name': name,
    }) as Map<String, dynamic>,
  );

  Future<List<PasskeyCredential>> listPasskeys() async {
    final data = await _send('GET', '/webauthn/credentials');
    return (data as List)
        .map((e) => PasskeyCredential.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> deletePasskey(String id) =>
      _send('DELETE', '/webauthn/credentials/$id');

  // --- Devices / pairing ---

  Future<List<Device>> listDevices() async {
    final data = await _send('GET', '/devices');
    return (data as List)
        .map((e) => Device.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Device> getDevice(String id) async =>
      Device.fromJson(await _send('GET', '/devices/$id') as Map<String, dynamic>);

  Future<Device> confirmPairing(String pairingCode) async {
    final data = await _send(
      'POST',
      '/pairing/confirm',
      body: {'pairing_code': pairingCode},
    ) as Map<String, dynamic>;
    return Device.fromJson(data['device'] as Map<String, dynamic>);
  }

  Future<void> revokeDevice(String id) =>
      _send('POST', '/devices/$id/revoke');

  // --- Authorization requests ---

  Future<Map<String, dynamic>> beginAuthorization(String pcId) async =>
      await _send('POST', '/auth/challenges', body: {
        'pc_id': pcId,
      }) as Map<String, dynamic>;

  Future<AuthRequest> createAuthorization({
    required String challengeId,
    required String pcId,
    required Map<String, dynamic> assertion,
    String operation = 'remote_unlock',
  }) async => AuthRequest.fromJson(
    await _send('POST', '/auth/requests', body: {
      'challenge_id': challengeId,
      'pc_id': pcId,
      'operation': operation,
      'assertion': assertion,
    }) as Map<String, dynamic>,
  );

  Future<AuthRequest> getRequest(String id) async => AuthRequest.fromJson(
    await _send('GET', '/requests/$id') as Map<String, dynamic>,
  );

  Future<List<AuthRequest>> listRequests({int limit = 50}) async {
    final data = await _send('GET', '/requests?limit=$limit');
    return (data as List)
        .map((e) => AuthRequest.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}
