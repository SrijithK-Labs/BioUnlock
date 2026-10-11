import 'package:flutter/foundation.dart';

import '../models/misc.dart';
import '../services/api_client.dart';
import '../services/api_exception.dart';
import '../services/passkey_service.dart';

/// Manages the account's passkeys (WebAuthn credentials).
class PasskeysController extends ChangeNotifier {
  PasskeysController({
    required ApiClient api,
    required PasskeyService passkeys,
    ApiClient Function()? apiProvider,
  }) : _api = api,
       _passkeys = passkeys,
       _apiProvider = apiProvider;

  final ApiClient _api;
  final PasskeyService _passkeys;
  final ApiClient Function()? _apiProvider;

  List<PasskeyCredential> _credentials = const [];
  bool _busy = false;
  String? _error;

  List<PasskeyCredential> get credentials => _credentials;
  bool get busy => _busy;
  String? get error => _error;

  ApiClient get _client => _apiProvider?.call() ?? _api;

  Future<void> load() async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      _credentials = await _client.listPasskeys();
    } on ApiException catch (error) {
      _error = error.message;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  /// Runs the full passkey registration flow: begin -> platform -> complete.
  Future<bool> registerPasskey({String? name}) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      final begin = await _client.passkeyRegisterBegin();
      final options = begin['options'] as Map<String, dynamic>;
      final credential = await _passkeys.register(options);
      await _client.passkeyRegisterComplete(
        challengeId: begin['challenge_id'] as String,
        credential: credential,
        name: name,
      );
      await load();
      return true;
    } on PasskeyException catch (error) {
      _error = error.message;
      return false;
    } on ApiException catch (error) {
      _error = error.message;
      return false;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<bool> deletePasskey(String id) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      await _client.deletePasskey(id);
      await load();
      return true;
    } on ApiException catch (error) {
      _error = error.message;
      return false;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }
}
