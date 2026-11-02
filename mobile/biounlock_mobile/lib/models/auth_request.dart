class AuthRequest {
  AuthRequest({
    required this.id,
    required this.pcId,
    required this.operation,
    required this.status,
    required this.createdAt,
    required this.expiresAt,
    this.pcName,
    this.deliveredAt,
    this.ackAt,
    this.ackReason,
  });

  final String id;
  final String pcId;
  final String? pcName;
  final String operation;
  final String status;
  final DateTime createdAt;
  final DateTime expiresAt;
  final DateTime? deliveredAt;
  final DateTime? ackAt;
  final String? ackReason;

  bool get isTerminal =>
      status == 'verified' ||
      status == 'rejected' ||
      status == 'completed' ||
      status == 'expired';

  bool get isPending => status == 'pending' || status == 'delivered';

  static DateTime? _parse(Object? value) =>
      value == null ? null : DateTime.parse(value as String);

  factory AuthRequest.fromJson(Map<String, dynamic> json) => AuthRequest(
    id: json['id'] as String,
    pcId: json['pc_id'] as String,
    pcName: json['pc_name'] as String?,
    operation: json['operation'] as String,
    status: json['status'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
    expiresAt: DateTime.parse(json['expires_at'] as String),
    deliveredAt: _parse(json['delivered_at']),
    ackAt: _parse(json['ack_at']),
    ackReason: json['ack_reason'] as String?,
  );
}
