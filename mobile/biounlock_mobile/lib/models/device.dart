import 'dart:convert';

class Device {
  Device({
    required this.id,
    required this.name,
    required this.platform,
    required this.status,
    required this.createdAt,
    this.pairedAt,
    this.lastSeenAt,
    this.revokedAt,
    this.isOnline = false,
  });

  final String id;
  final String name;
  final String platform;
  final String status;
  final DateTime createdAt;
  final DateTime? pairedAt;
  final DateTime? lastSeenAt;
  final DateTime? revokedAt;
  final bool isOnline;

  bool get isActive => status == 'active';
  bool get isRevoked => status == 'revoked';
  bool get isPending => status == 'pending';

  static DateTime? _parse(Object? value) =>
      value == null ? null : DateTime.parse(value as String);

  factory Device.fromJson(Map<String, dynamic> json) => Device(
    id: json['id'] as String,
    name: json['name'] as String,
    platform: json['platform'] as String,
    status: json['status'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
    pairedAt: _parse(json['paired_at']),
    lastSeenAt: _parse(json['last_seen_at']),
    revokedAt: _parse(json['revoked_at']),
    isOnline: json['is_online'] as bool? ?? false,
  );
}

/// The contents of the QR code the PC agent displays during enrollment.
class PairingPayload {
  PairingPayload({
    required this.version,
    required this.type,
    required this.deviceId,
    required this.deviceName,
    required this.pairingCode,
    required this.serverFingerprint,
    this.serverUrl,
  });

  final int version;
  final String type;
  final String deviceId;
  final String deviceName;
  final String pairingCode;
  final String serverFingerprint;
  final String? serverUrl;

  factory PairingPayload.fromJson(Map<String, dynamic> json) => PairingPayload(
    version: (json['v'] as num?)?.toInt() ?? 0,
    type: json['type'] as String? ?? '',
    deviceId: json['device_id'] as String? ?? '',
    deviceName: json['device_name'] as String? ?? '',
    pairingCode: json['pairing_code'] as String? ?? '',
    serverFingerprint: json['server_fingerprint'] as String? ?? '',
    serverUrl: json['server_url'] as String?,
  );

  /// Parses a scanned QR string. Throws [FormatException] when invalid.
  factory PairingPayload.parse(String raw) {
    final Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      throw const FormatException('Not a BioUnlock pairing code.');
    }
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Not a BioUnlock pairing code.');
    }
    final payload = PairingPayload.fromJson(decoded);
    if (payload.type != 'biounlock-pairing' || payload.pairingCode.isEmpty) {
      throw const FormatException('Not a BioUnlock pairing code.');
    }
    return payload;
  }
}
