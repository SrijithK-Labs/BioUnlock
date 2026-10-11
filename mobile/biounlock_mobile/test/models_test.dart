import 'package:biounlock_mobile/models/auth_request.dart';
import 'package:biounlock_mobile/models/device.dart';
import 'package:biounlock_mobile/models/misc.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

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

  test('Device parses objects without an account_id field', () {
    final device = Device.fromJson(deviceJson(online: false));
    expect(device.id, 'dev-1');
    expect(device.name, 'Workstation');
    expect(device.isActive, isTrue);
    expect(device.isOnline, isFalse);
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

  test('ServerInfo parses the new contract fields', () {
    final info = ServerInfo.fromJson(serverInfoJson(version: '2.0.0'));
    expect(info.name, 'BioUnlock');
    expect(info.version, '2.0.0');
    expect(info.signingKeyFingerprint, 'abc');
    expect(info.environment, 'production');
  });

  test('PasskeyCredential parses created/last-used fields', () {
    final credential = PasskeyCredential.fromJson({
      'id': 'cred-1',
      'name': 'Pixel',
      'created_at': '2026-01-01T00:00:00Z',
      'last_used_at': '2026-01-02T00:00:00Z',
    });
    expect(credential.id, 'cred-1');
    expect(credential.name, 'Pixel');
    expect(credential.lastUsedAt, isNotNull);
  });

  test('SecurityEvent parses device_id', () {
    final event = SecurityEvent.fromJson({
      'id': 7,
      'event_type': 'device_revoked',
      'detail': 'Device revoked',
      'device_id': 'dev-1',
      'created_at': '2026-01-01T00:00:00Z',
    });
    expect(event.id, 7);
    expect(event.deviceId, 'dev-1');
    expect(event.eventType, 'device_revoked');
  });

  test('AuthRequest parses the request contract', () {
    final request = AuthRequest.fromJson(
      requestJson(status: 'rejected', reason: 'user_denied'),
    );
    expect(request.pcId, 'dev-1');
    expect(request.pcName, 'Workstation');
    expect(request.ackReason, 'user_denied');
    expect(request.isTerminal, isTrue);
  });
}