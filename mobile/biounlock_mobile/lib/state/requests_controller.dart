import 'package:flutter/foundation.dart';

import '../config.dart';
import '../models/auth_request.dart';
import '../services/api_client.dart';
import '../services/api_exception.dart';
import '../services/passkey_service.dart';

/// Result of an authorization attempt. The status is what the *server* knows,
/// never an optimistic guess.
class AuthorizationOutcome {
  AuthorizationOutcome({required this.status, this.request, this.message});

  final String status;
  final AuthRequest? request;
  final String? message;

  bool get succeeded => status == 'verified';
  bool get failed => status == 'rejected' || status == 'expired';
}

/// Drives the remote-authorization flow and polls for the truthful result.
class RequestsController extends ChangeNotifier {
  RequestsController({
    required ApiClient api,
    required PasskeyService passkeys,
    ApiClient Function()? apiProvider,
    Duration? pollInterval,
    Duration? pollTimeout,
    Future<void> Function(Duration)? delay,
  }) : _api = api,
       _passkeys = passkeys,
       _apiProvider = apiProvider,
       _pollInterval = pollInterval ?? AppConfig.statusPollInterval,
       _pollTimeout = pollTimeout ?? AppConfig.statusPollTimeout,
       _delay = delay ?? Future<void>.delayed;

  final ApiClient _api;
  final PasskeyService _passkeys;
  final ApiClient Function()? _apiProvider;
  final Duration _pollInterval;
  final Duration _pollTimeout;
  final Future<void> Function(Duration) _delay;

  List<AuthRequest> _requests = const [];
  bool _busy = false;
  String? _error;
  String? _stage;
  AuthRequest? _current;

  List<AuthRequest> get requests => _requests;
  bool get busy => _busy;
  String? get error => _error;
  String? get stage => _stage;
  AuthRequest? get current => _current;

  ApiClient get _client => _apiProvider?.call() ?? _api;

  Future<void> load() async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      _requests = await _client.listRequests();
    } on ApiException catch (error) {
      _error = error.message;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  /// Full flow: challenge -> passkey assertion -> create request -> poll.
  Future<AuthorizationOutcome> authorize({required String pcId}) async {
    _busy = true;
    _error = null;
    _current = null;
    _stage = 'Requesting a challenge…';
    notifyListeners();
    try {
      final begin = await _client.beginAuthorization(pcId);
      final options = begin['options'] as Map<String, dynamic>;

      _stage = 'Waiting for your biometric confirmation…';
      notifyListeners();
      final assertion = await _passkeys.authenticate(options);

      _stage = 'Submitting authorization…';
      notifyListeners();
      final created = await _client.createAuthorization(
        challengeId: begin['challenge_id'] as String,
        pcId: begin['pc_id'] as String? ?? pcId,
        assertion: assertion,
      );
      _current = created;

      final finished = await _poll(created.id);
      _current = finished;
      await load();
      return AuthorizationOutcome(
        status: finished.status,
        request: finished,
      );
    } on PasskeyException catch (error) {
      _error = error.message;
      return AuthorizationOutcome(status: 'error', message: error.message);
    } on ApiException catch (error) {
      _error = error.message;
      return AuthorizationOutcome(status: 'error', message: error.message);
    } finally {
      _busy = false;
      _stage = null;
      notifyListeners();
    }
  }

  Future<AuthRequest> _poll(String requestId) async {
    final deadline = DateTime.now().add(_pollTimeout);
    _stage = 'Waiting for the PC to verify…';
    notifyListeners();
    var latest = await _client.getRequest(requestId);
    while (!latest.isTerminal && DateTime.now().isBefore(deadline)) {
      await _delay(_pollInterval);
      latest = await _client.getRequest(requestId);
      _current = latest;
      notifyListeners();
    }
    return latest;
  }
}
