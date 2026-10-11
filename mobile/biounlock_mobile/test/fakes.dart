import 'dart:convert';

import 'package:biounlock_mobile/services/passkey_service.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// A passkey service that returns deterministic, well-formed responses without
/// touching the platform.
class FakePasskeyService implements PasskeyService {
  FakePasskeyService({this.failWith});

  /// When set, [register]/[authenticate] throw this.
  final PasskeyException? failWith;

  int registerCalls = 0;
  int authenticateCalls = 0;

  @override
  Future<Map<String, dynamic>> register(Map<String, dynamic> options) async {
    registerCalls++;
    if (failWith != null) throw failWith!;
    return {
      'id': 'cred-id',
      'rawId': 'cred-id',
      'type': 'public-key',
      'response': {
        'clientDataJSON': 'client',
        'attestationObject': 'attestation',
      },
      'clientExtensionResults': <String, dynamic>{},
    };
  }

  @override
  Future<Map<String, dynamic>> authenticate(Map<String, dynamic> options) async {
    authenticateCalls++;
    if (failWith != null) throw failWith!;
    return {
      'id': 'cred-id',
      'rawId': 'cred-id',
      'type': 'public-key',
      'response': {
        'clientDataJSON': 'client',
        'authenticatorData': 'authdata',
        'signature': 'sig',
        'userHandle': '',
      },
      'clientExtensionResults': <String, dynamic>{},
    };
  }
}

Map<String, dynamic> jsonResponse(Object? body, {int status = 200}) =>
    {'status': status, 'body': body};

/// Builds a [MockClient] from a map of `"METHOD /path"` -> handler.
MockClient routedClient(
  Map<String, http.Response Function(http.Request request)> routes,
) {
  return MockClient((request) async {
    final key = '${request.method} ${request.url.path}';
    final handler = routes[key];
    if (handler == null) {
      return http.Response(
        jsonEncode({
          'error': {'code': 'not_found', 'message': 'No route for $key'},
        }),
        404,
        headers: {'content-type': 'application/json'},
      );
    }
    return handler(request);
  });
}

http.Response ok(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json'},
);

http.Response errorResponse(Object body, int status) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json'},
);

Map<String, dynamic> accountJson({String email = 'user@example.com'}) => {
  'id': 'acc-1',
  'email': email,
  'created_at': '2026-01-01T00:00:00Z',
};

Map<String, dynamic> sessionJson({String email = 'user@example.com'}) => {
  'token': 'session-token',
  'token_type': 'bearer',
  'expires_at': '2999-01-01T00:00:00Z',
  'account': accountJson(email: email),
};

Map<String, dynamic> deviceJson({
  String id = 'dev-1',
  String name = 'Workstation',
  String status = 'active',
  bool online = true,
}) => {
  'id': id,
  'name': name,
  'platform': 'windows',
  'status': status,
  'created_at': '2026-01-01T00:00:00Z',
  'paired_at': '2026-01-01T00:00:00Z',
  'last_seen_at': '2026-01-01T00:00:00Z',
  'revoked_at': null,
  'is_online': online,
  'account_id': 'acc-1',
};

Map<String, dynamic> requestJson({
  String id = 'req-1',
  String status = 'verified',
  String? reason,
  String operation = 'remote_unlock',
}) => {
  'id': id,
  'pc_id': 'dev-1',
  'pc_name': 'Workstation',
  'operation': operation,
  'status': status,
  'created_at': '2026-01-01T00:00:00Z',
  'expires_at': '2999-01-01T00:00:00Z',
  'delivered_at': null,
  'ack_at': null,
  'ack_reason': reason,
};
