import 'package:biounlock_mobile/models/device.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PairingPayload', () {
    test('parses a valid QR payload', () {
      final payload = PairingPayload.parse(
        '{"v":1,"type":"biounlock-pairing","device_id":"d1",'
        '"device_name":"Workstation","pairing_code":"ABCDEFGH",'
        '"server_fingerprint":"fp","server_url":null}',
      );
      expect(payload.deviceId, 'd1');
      expect(payload.deviceName, 'Workstation');
      expect(payload.pairingCode, 'ABCDEFGH');
      expect(payload.serverFingerprint, 'fp');
      expect(payload.serverUrl, isNull);
    });

    test('rejects foreign QR payloads', () {
      expect(
        () => PairingPayload.parse('{"type":"something-else"}'),
        throwsFormatException,
      );
    });

    test('rejects non-JSON', () {
      expect(() => PairingPayload.parse('not json'), throwsFormatException);
    });
  });

  test('Device exposes status helpers', () {
    final device = Device(
      id: 'd1',
      name: 'PC',
      platform: 'windows',
      status: 'active',
      createdAt: DateTime.utc(2026),
      isOnline: true,
    );
    expect(device.isActive, isTrue);
    expect(device.isRevoked, isFalse);
    expect(device.isOnline, isTrue);
  });
}
