import 'dart:convert';

/// Thrown when the backend returns an error response.
///
/// Mirrors the server contract `{"error": {"code": ..., "message": ...}}`.
class ApiException implements Exception {
  ApiException(this.statusCode, this.code, this.message);

  final int statusCode;
  final String code;
  final String message;

  /// Parses a JSON error body, falling back to safe defaults.
  factory ApiException.fromBody(int statusCode, String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final error = decoded['error'];
        if (error is Map<String, dynamic>) {
          return ApiException(
            statusCode,
            (error['code'] as String?) ?? 'http_$statusCode',
            (error['message'] as String?) ?? 'Request failed.',
          );
        }
        final detail = decoded['detail'];
        if (detail is String) {
          return ApiException(statusCode, 'http_$statusCode', detail);
        }
      }
    } catch (_) {
      // fall through to a generic message
    }
    return ApiException(statusCode, 'http_$statusCode', 'Request failed.');
  }

  @override
  String toString() => message;
}
