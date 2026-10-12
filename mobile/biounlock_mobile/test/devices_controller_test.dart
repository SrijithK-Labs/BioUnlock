import 'package:biounlock_mobile/services/api_client.dart';
import 'package:biounlock_mobile/state/devices_controller.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'fakes.dart';

void main() {
  test('remove deletes a revoked device and refreshes the list', () async {
    var devices = [deviceJson(id: 'dev-1', status: 'revoked')];
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'GET /api/v1/devices': (_) => ok(devices),
        'DELETE /api/v1/devices/dev-1': (_) {
          devices = [];
          return http.Response('', 204);
        },
      }),
    );
    final controller = DevicesController(api: client);
    await controller.load();
    expect(controller.devices, hasLength(1));

    final removed = await controller.remove('dev-1');

    expect(removed, isTrue);
    expect(controller.devices, isEmpty);
  });

  test('remove surfaces the server error', () async {
    final client = ApiClient(
      baseUrl: 'https://example.com',
      httpClient: routedClient({
        'GET /api/v1/devices': (_) => ok([deviceJson(status: 'revoked')]),
        'DELETE /api/v1/devices/dev-1': (_) => errorResponse({
          'error': {
            'code': 'http_409',
            'message': 'Revoke the PC before removing it.',
          },
        }, 409),
      }),
    );
    final controller = DevicesController(api: client);
    await controller.load();

    final removed = await controller.remove('dev-1');

    expect(removed, isFalse);
    expect(controller.error, contains('Revoke'));
  });
}
