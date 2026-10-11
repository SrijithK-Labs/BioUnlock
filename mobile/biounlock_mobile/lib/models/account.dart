class Account {
  Account({required this.id, required this.email, required this.createdAt});

  final String id;
  final String email;
  final DateTime createdAt;

  factory Account.fromJson(Map<String, dynamic> json) => Account(
    id: json['id'] as String,
    email: json['email'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
  );
}

/// A server-issued session (bearer token) bound to an account.
class Session {
  Session({
    required this.token,
    required this.expiresAt,
    required this.account,
  });

  final String token;
  final DateTime expiresAt;
  final Account account;

  bool get isExpired => DateTime.now().toUtc().isAfter(expiresAt.toUtc());

  factory Session.fromJson(Map<String, dynamic> json) => Session(
    token: json['token'] as String,
    expiresAt: DateTime.parse(json['expires_at'] as String),
    account: Account.fromJson(json['account'] as Map<String, dynamic>),
  );

  Map<String, dynamic> toJson() => {
    'token': token,
    'expires_at': expiresAt.toUtc().toIso8601String(),
    'account': {
      'id': account.id,
      'email': account.email,
      'created_at': account.createdAt.toUtc().toIso8601String(),
    },
  };
}
