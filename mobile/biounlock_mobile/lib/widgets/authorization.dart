import 'package:flutter/material.dart';

import '../state/requests_controller.dart';
import '../theme.dart';

/// Turns an [AuthorizationOutcome] into a friendly sentence for the user.
String authorizationMessage(AuthorizationOutcome outcome, String operation) {
  final reason = outcome.request?.ackReason;
  switch (outcome.status) {
    case 'verified':
      if (reason == 'already_unlocked') return 'This PC is already unlocked.';
      if (reason == 'already_locked') return 'This PC is already locked.';
      return operation == 'remote_lock'
          ? 'The PC was locked.'
          : 'The PC was unlocked.';
    case 'rejected':
      if (reason == 'lock_failed') return 'The PC could not be locked.';
      return 'The PC rejected the request.${reason != null ? ' ($reason)' : ''}';
    case 'expired':
      return 'The request expired before the PC responded.';
    default:
      return outcome.message ?? 'Authorization could not be completed.';
  }
}

/// Shows the truthful result of an authorization attempt after the fact.
Future<void> showAuthorizationResult(
  BuildContext context,
  AuthorizationOutcome outcome,
  String operation,
) {
  final scheme = context.scheme;
  final tokens = context.tokens;
  final succeeded = outcome.succeeded;
  final color = succeeded
      ? tokens.success
      : outcome.failed
      ? scheme.error
      : scheme.onSurfaceVariant;
  final icon = succeeded
      ? Icons.verified_rounded
      : outcome.failed
      ? Icons.gpp_bad_rounded
      : Icons.help_outline_rounded;
  return showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      icon: Icon(icon, color: color, size: 32),
      title: Text(succeeded ? 'Done' : 'Not completed'),
      content: Text(authorizationMessage(outcome, operation)),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('OK'),
        ),
      ],
    ),
  );
}
