import 'dart:convert';

import 'package:biounlock_mobile/services/api_client.dart';
import 'package:biounlock_mobile/services/passkey_service.dart';
import 'package:biounlock_mobile/state/requests_controller.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  RequestsController buildController({
    required Map<String, dynamic> Function(int call) statusForPoll,
    FakePasskeyService? passkeys,
  }) {
    var pollCall = 0;
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'POST /api/v1/auth/challenges': (_) => ok({
          'challenge_id': 'chal-1',
          'options': {
            'challenge': 'abc',
            'rpId': 'example.com',
            'allowCredentials': [
              {'type': 'public-key', 'id': 'cred-id'},
            ],
            'userVerification': 'required',
          },
          'rp_id': 'example.com',
          'expires_at': '2999-01-01T00:00:00Z',
          'pc_id': 'dev-1',
          'pc_name': 'Workstation',
        }),
        'POST /api/v1/auth/requests': (_) =>
            ok(requestJson(status: 'pending'), 201),
        'GET /api/v1/requests/req-1': (_) {
          final body = statusForPoll(pollCall);
          pollCall++;
          return ok(body);
        },
        'GET /api/v1/requests': (_) => ok([requestJson(status: 'verified')]),
      }),
    );
    return RequestsController(
      api: client,
      passkeys: passkeys ?? FakePasskeyService(),
      pollInterval: Duration.zero,
      delay: (_) async {},
    );
  }

  test('authorize polls until verified and reports truthful status', () async {
    final controller = buildController(
      statusForPoll: (call) => requestJson(
        status: call == 0 ? 'pending' : 'verified',
      ),
    );
    final outcome = await controller.authorize(pcId: 'dev-1');
    expect(outcome.succeeded, isTrue);
    expect(outcome.request?.status, 'verified');
    expect(controller.error, isNull);
  });

  test('authorize surfaces rejection with the reason code', () async {
    final controller = buildController(
      statusForPoll: (call) => requestJson(
        status: call == 0 ? 'delivered' : 'rejected',
        reason: 'user_denied',
      ),
    );
    final outcome = await controller.authorize(pcId: 'dev-1');
    expect(outcome.failed, isTrue);
    expect(outcome.request?.ackReason, 'user_denied');
  });

  test('authorize reports cancelling the passkey as an error', () async {
    final controller = buildController(
      statusForPoll: (_) => requestJson(status: 'verified'),
      passkeys: FakePasskeyService(
        failWith: PasskeyException('Authentication was cancelled.', cancelled: true),
      ),
    );
    final outcome = await controller.authorize(pcId: 'dev-1');
    expect(outcome.status, 'error');
    expect(controller.error, contains('cancelled'));
  });

  test('authorize sends the requested operation to the server', () async {
    Map<String, dynamic>? captured;
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'POST /api/v1/auth/challenges': (_) => ok({
          'challenge_id': 'chal-1',
          'options': {
            'challenge': 'abc',
            'rpId': 'example.com',
            'allowCredentials': [
              {'type': 'public-key', 'id': 'cred-id'},
            ],
            'userVerification': 'required',
          },
          'rp_id': 'example.com',
          'expires_at': '2999-01-01T00:00:00Z',
          'pc_id': 'dev-1',
          'pc_name': 'Workstation',
        }),
        'POST /api/v1/auth/requests': (request) {
          captured = jsonDecode(request.body) as Map<String, dynamic>;
          return ok(requestJson(status: 'pending'), 201);
        },
        'GET /api/v1/requests/req-1': (_) => ok(requestJson(status: 'verified')),
        'GET /api/v1/requests': (_) => ok([requestJson(status: 'verified')]),
      }),
    );
    final controller = RequestsController(
      api: client,
      passkeys: FakePasskeyService(),
      pollInterval: Duration.zero,
      delay: (_) async {},
    );

    await controller.authorize(pcId: 'dev-1', operation: 'remote_lock');

    expect(captured?['operation'], 'remote_lock');
  });
}
