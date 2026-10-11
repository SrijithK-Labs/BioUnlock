import 'package:biounlock_mobile/services/api_client.dart';
import 'package:biounlock_mobile/services/api_exception.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'fakes.dart';

void main() {
  test('serverInfo parses fields', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok({
          'name': 'BioUnlock',
          'version': '0.1.0',
          'rp_id': 'example.com',
          'server_signing_key_fingerprint': 'abc',
          'environment': 'production',
        }),
      }),
    );
    final info = await client.serverInfo();
    expect(info.version, '0.1.0');
    expect(info.rpId, 'example.com');
  });

  test('register stores session', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'POST /api/v1/auth/register': (_) => ok(sessionJson(), 201),
      }),
    );
    final session = await client.register('user@example.com', 'password123');
    expect(session.token, 'session-token');
    expect(session.account.email, 'user@example.com');
    expect(session.isExpired, isFalse);
  });

  test('parses structured error bodies', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'POST /api/v1/auth/login': (_) => errorResponse({
          'error': {'code': 'http_401', 'message': 'Invalid email or password.'},
        }, 401),
      }),
    );
    expect(
      () => client.login('user@example.com', 'wrong'),
      throwsA(
        isA<ApiException>()
            .having((e) => e.statusCode, 'status', 401)
            .having((e) => e.message, 'message', 'Invalid email or password.'),
      ),
    );
  });

  test('prepareEndpoint normalizes trailing slash in base url', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com/',
      httpClient: routedClient({
        'GET /api/v1/devices': (_) => ok([deviceJson()]),
      }),
    );
    final devices = await client.listDevices();
    expect(devices, hasLength(1));
    expect(devices.first.name, 'Workstation');
  });

  test('sends bearer token when set', () async {
    String? seenAuth;
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'GET /api/v1/auth/me': (request) {
          seenAuth = request.headers['Authorization'];
          return ok(accountJson());
        },
      }),
    );
    client.token = 'tok-123';
    await client.me();
    expect(seenAuth, 'Bearer tok-123');
  });

  test('network failure becomes ApiException', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: MockThrowingClient(),
    );
    expect(
      () => client.serverInfo(),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', 'network_error')),
    );
  });
}

class MockThrowingClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    throw Exception('boom');
  }
}
