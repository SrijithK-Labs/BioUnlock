import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/auth_request.dart';
import '../models/device.dart';
import '../models/misc.dart';
import 'api_exception.dart';

/// Thin, typed wrapper around the BioUnlock REST API.
///
/// The base URL and the shared API token are supplied by the user at setup time
/// (each deployment is self-hosted) and never hardcoded. Owner endpoints expect
/// the token as ``Authorization: Bearer <token>``; the PC agent authenticates
/// separately, so a missing token simply omits the header. Passkey changes also
/// send the optional enrollment token as ``X-BioUnlock-Enrollment``.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    this.apiToken,
    this.enrollmentToken,
    http.Client? httpClient,
  }) : _http = httpClient ?? http.Client();

  final String baseUrl;
  final String? apiToken;
  final String? enrollmentToken;
  final http.Client _http;

  Uri _uri(String path) {
    final normalized = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    return Uri.parse('$normalized/api/v1$path');
  }

  Map<String, String> _headers({
    Map<String, String>? extra,
    bool enrollment = false,
  }) {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    };
    if (apiToken != null && apiToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $apiToken';
    }
    if (enrollment &&
        enrollmentToken != null &&
        enrollmentToken!.isNotEmpty) {
      headers['X-BioUnlock-Enrollment'] = enrollmentToken!;
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
    bool enrollment = false,
  }) async {
    final request = http.Request(method, _uri(path))
      ..headers.addAll(_headers(extra: headers, enrollment: enrollment))
      ..followRedirects = false;
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

  Future<List<SecurityEvent>> securityEvents({int limit = 50, int days = 30}) async {
    final data = await _send('GET', '/security-events?limit=$limit&days=$days');
    return (data as List)
        .map((e) => SecurityEvent.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // --- WebAuthn / passkeys ---

  Future<Map<String, dynamic>> passkeyRegisterBegin() async =>
      await _send(
        'POST',
        '/webauthn/register/begin',
        enrollment: true,
      ) as Map<String, dynamic>;

  Future<PasskeyCredential> passkeyRegisterComplete({
    required String challengeId,
    required Map<String, dynamic> credential,
    String? name,
  }) async => PasskeyCredential.fromJson(
    await _send(
      'POST',
      '/webauthn/register/complete',
      body: {
        'challenge_id': challengeId,
        'credential': credential,
        'name': name,
      },
      enrollment: true,
    ) as Map<String, dynamic>,
  );

  Future<List<PasskeyCredential>> listPasskeys() async {
    final data = await _send('GET', '/webauthn/credentials');
    return (data as List)
        .map((e) => PasskeyCredential.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> deletePasskey(String id) =>
      _send('DELETE', '/webauthn/credentials/$id', enrollment: true);

  // --- Devices / pairing ---

  Future<Map<String, dynamic>> enrollDevice({
    required String name,
    required String platform,
    required String publicKey,
  }) async => await _send('POST', '/devices/enroll', body: {
    'name': name,
    'platform': platform,
    'public_key': publicKey,
  }) as Map<String, dynamic>;

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

  /// Permanently removes a revoked PC (and its server-side history).
  Future<void> deleteDevice(String id) =>
      _send('DELETE', '/devices/$id');

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

  Future<List<AuthRequest>> listRequests({int limit = 50, int days = 30}) async {
    final data = await _send('GET', '/requests?limit=$limit&days=$days');
    return (data as List)
        .map((e) => AuthRequest.fromJson(e as Map<String, dynamic>))
        .toList();
  }
}
