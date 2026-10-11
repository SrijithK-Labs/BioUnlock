import 'dart:convert';

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
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
      }),
    );
    final info = await client.serverInfo();
    expect(info.version, '0.1.0');
    expect(info.rpId, 'example.com');
  });

  test('parses structured error bodies', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'GET /api/v1/webauthn/credentials': (_) => errorResponse({
          'error': {'code': 'http_401', 'message': 'Invalid email or password.'},
        }, 401),
      }),
    );
    expect(
      () => client.listPasskeys(),
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

  test('sends no Authorization header on any request', () async {
    final seenHeaders = <String?>[];
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'GET /api/v1/devices': (request) {
          seenHeaders.add(request.headers['Authorization']);
          return ok([deviceJson()]);
        },
      }),
    );
    await client.listDevices();
    expect(seenHeaders, [null]);
  });

  test('enrollDevice posts name, platform and public key', () async {
    Map<String, dynamic>? captured;
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'POST /api/v1/devices/enroll': (request) {
          captured = jsonDecode(request.body) as Map<String, dynamic>;
          return ok({
            'device_id': 'dev-9',
            'device_name': 'Laptop',
            'pairing_code': 'ABCDEF',
            'qr_payload': 'x',
            'expires_at': '2026-01-02T00:00:00Z',
            'server_signing_public_key': 'pub',
            'server_signing_key_fingerprint': 'fp',
          });
        },
      }),
    );
    final result = await client.enrollDevice(
      name: 'Laptop',
      platform: 'windows',
      publicKey: 'pub',
    );
    expect(result['device_id'], 'dev-9');
    expect(captured?['name'], 'Laptop');
    expect(captured?['platform'], 'windows');
    expect(captured?['public_key'], 'pub');
  });

  test('confirmPairing parses the nested device object', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'POST /api/v1/pairing/confirm': (_) => ok({
          'device': deviceJson(name: 'Laptop'),
          'paired_at': '2026-01-01T00:00:00Z',
        }),
      }),
    );
    final device = await client.confirmPairing('ABC123');
    expect(device.name, 'Laptop');
    expect(device.isActive, isTrue);
  });

  test('passkey registration complete parses the credential', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'POST /api/v1/webauthn/register/complete': (_) => ok({
          'id': 'cred-1',
          'name': 'Pixel',
          'created_at': '2026-01-01T00:00:00Z',
          'last_used_at': null,
        }),
      }),
    );
    final credential = await client.passkeyRegisterComplete(
      challengeId: 'chal-1',
      credential: {'id': 'x'},
      name: 'Pixel',
    );
    expect(credential.id, 'cred-1');
    expect(credential.name, 'Pixel');
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

dynamic jsonDecodeCompat(String body) => body.isEmpty ? null : jsonDecode(body);

class MockThrowingClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    throw Exception('boom');
  }
}