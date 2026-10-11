class PasskeyCredential {
  PasskeyCredential({
    required this.id,
    required this.createdAt,
    this.name,
    this.lastUsedAt,
  });

  final String id;
  final String? name;
  final DateTime createdAt;
  final DateTime? lastUsedAt;

  factory PasskeyCredential.fromJson(Map<String, dynamic> json) =>
      PasskeyCredential(
        id: json['id'] as String,
        name: json['name'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
        lastUsedAt: json['last_used_at'] == null
            ? null
            : DateTime.parse(json['last_used_at'] as String),
      );
}

class SecurityEvent {
  SecurityEvent({
    required this.id,
    required this.eventType,
    required this.detail,
    required this.createdAt,
    this.deviceId,
  });

  final int id;
  final String eventType;
  final String detail;
  final String? deviceId;
  final DateTime createdAt;

  factory SecurityEvent.fromJson(Map<String, dynamic> json) => SecurityEvent(
    id: (json['id'] as num).toInt(),
    eventType: json['event_type'] as String,
    detail: json['detail'] as String,
    deviceId: json['device_id'] as String?,
    createdAt: DateTime.parse(json['created_at'] as String),
  );
}

class ServerInfo {
  ServerInfo({
    required this.name,
    required this.version,
    required this.rpId,
    required this.signingKeyFingerprint,
    required this.environment,
  });

  final String name;
  final String version;
  final String rpId;
  final String signingKeyFingerprint;
  final String environment;

  factory ServerInfo.fromJson(Map<String, dynamic> json) => ServerInfo(
    name: json['name'] as String,
    version: json['version'] as String,
    rpId: json['rp_id'] as String,
    signingKeyFingerprint: json['server_signing_key_fingerprint'] as String,
    environment: json['environment'] as String,
  );
}
