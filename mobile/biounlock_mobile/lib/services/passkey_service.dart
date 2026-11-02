import 'package:passkeys/authenticator.dart';
import 'package:passkeys/types.dart';

/// A passkey operation failing in a way the UI should surface.
class PasskeyException implements Exception {
  PasskeyException(this.message, {this.cancelled = false});

  final String message;
  final bool cancelled;

  @override
  String toString() => message;
}

/// Abstracts the platform passkey (WebAuthn) authenticator so screens and tests
/// do not depend on the concrete plugin.
abstract class PasskeyService {
  /// Creates a passkey from server registration options and returns the
  /// credential JSON to forward to the backend.
  Future<Map<String, dynamic>> register(Map<String, dynamic> options);

  /// Signs the server authentication options and returns the assertion JSON.
  Future<Map<String, dynamic>> authenticate(Map<String, dynamic> options);
}

/// [PasskeyService] backed by the `passkeys` plugin (Android/iOS/desktop).
class PlatformPasskeyService implements PasskeyService {
  PlatformPasskeyService({PasskeyAuthenticator? authenticator})
    : _authenticator = authenticator ?? PasskeyAuthenticator();

  final PasskeyAuthenticator _authenticator;

  @override
  Future<Map<String, dynamic>> register(Map<String, dynamic> options) async {
    final normalized = _normalizeOptions(options);
    final request = RegisterRequestType.fromJson(normalized);
    try {
      final response = await _authenticator.register(request);
      return response.toJson();
    } on PasskeyAuthCancelledException {
      throw PasskeyException('Passkey creation was cancelled.', cancelled: true);
    } on PasskeyException {
      rethrow;
    } catch (error) {
      throw PasskeyException(_humanError(error));
    }
  }

  @override
  Future<Map<String, dynamic>> authenticate(Map<String, dynamic> options) async {
    final normalized = _normalizeOptions(options);
    final request = AuthenticateRequestType.fromJson(normalized);
    try {
      final response = await _authenticator.authenticate(request);
      return response.toJson();
    } on PasskeyAuthCancelledException {
      throw PasskeyException('Authentication was cancelled.', cancelled: true);
    } on NoCredentialsAvailableException {
      throw PasskeyException('No passkey is available on this device.');
    } on PasskeyException {
      rethrow;
    } catch (error) {
      throw PasskeyException(_humanError(error));
    }
  }

  /// The `passkeys` plugin requires `transports` on credential descriptors, but
  /// the backend (python `webauthn`) omits it. Fill in an empty list.
  Map<String, dynamic> _normalizeOptions(Map<String, dynamic> options) {
    final copy = Map<String, dynamic>.from(options);
    for (final key in ['allowCredentials', 'excludeCredentials']) {
      final list = copy[key];
      if (list is List) {
        copy[key] = [
          for (final entry in list)
            if (entry is Map)
              {
                ...entry,
                if (!entry.containsKey('transports')) 'transports': <String>[],
              }
            else
              entry,
        ];
      }
    }
    return copy;
  }

  String _humanError(Object error) {
    final text = error.toString();
    if (text.contains('cancelled') || text.contains('canceled')) {
      return 'The operation was cancelled.';
    }
    return 'Passkey operation failed: $text';
  }
}
