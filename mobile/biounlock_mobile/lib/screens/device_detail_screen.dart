import 'package:flutter/material.dart';

import '../models/device.dart';
import '../state/devices_controller.dart';
import '../state/requests_controller.dart';
import '../widgets/status_pill.dart';

class DeviceDetailScreen extends StatelessWidget {
  const DeviceDetailScreen({
    super.key,
    required this.device,
    required this.devices,
    required this.requests,
  });

  final Device device;
  final DevicesController devices;
  final RequestsController requests;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(device.name)),
      body: AnimatedBuilder(
        animation: Listenable.merge([devices, requests]),
        builder: (context, _) => ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            _header(context),
            const SizedBox(height: 16),
            _details(context),
            const SizedBox(height: 16),
            _actions(context),
            const SizedBox(height: 24),
            _dangerZone(context),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: scheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Icon(
                device.isOnline
                    ? Icons.desktop_windows
                    : Icons.desktop_access_disabled,
                size: 28,
                color: device.isOnline ? scheme.primary : scheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(device.name, style: theme.textTheme.titleLarge),
                  const SizedBox(height: 8),
                  StatusPill(label: _statusLabel(), color: _statusColor(scheme)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _details(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Column(
          children: [
            _row(context, 'Platform', device.platform),
            _row(
              context,
              'Last seen',
              device.lastSeenAt?.toLocal().toString() ?? 'Never',
            ),
            if (device.pairedAt != null)
              _row(context, 'Paired at', device.pairedAt!.toLocal().toString()),
          ],
        ),
      ),
    );
  }

  Widget _actions(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            FilledButton.icon(
              onPressed: (!device.isActive || requests.busy)
                  ? null
                  : () => _authorize(context, 'remote_unlock'),
              icon: const Icon(Icons.lock_open),
              label: Text(requests.busy ? 'Working…' : 'Unlock this PC'),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: (!device.isActive || requests.busy)
                  ? null
                  : () => _authorize(context, 'remote_lock'),
              icon: const Icon(Icons.lock_outline),
              label: const Text('Lock this PC'),
            ),
            if (requests.error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  requests.error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (requests.stage != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Row(
                  children: [
                    const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    const SizedBox(width: 12),
                    Expanded(child: Text(requests.stage!)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _dangerZone(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Danger zone',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 4),
            Text(
              device.isRevoked
                  ? 'This PC is revoked and can be removed permanently.'
                  : 'Revoking blocks this PC from receiving unlock requests.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            if (device.isRevoked)
              FilledButton.icon(
                onPressed: devices.busy ? null : () => _delete(context),
                icon: const Icon(Icons.delete_outline),
                label: const Text('Delete this PC'),
                style: FilledButton.styleFrom(
                  backgroundColor: scheme.error,
                  foregroundColor: scheme.onError,
                ),
              )
            else
              OutlinedButton.icon(
                onPressed: devices.busy ? null : () => _revoke(context),
                icon: const Icon(Icons.block),
                label: const Text('Revoke access'),
                style: OutlinedButton.styleFrom(foregroundColor: scheme.error),
              ),
          ],
        ),
      ),
    );
  }

  String _statusLabel() {
    if (device.isRevoked) return 'Revoked';
    if (device.isOnline) return 'Online';
    if (device.isPending) return 'Awaiting pairing';
    return 'Paired';
  }

  Color _statusColor(ColorScheme scheme) {
    if (device.isRevoked) return scheme.error;
    if (device.isOnline) return const Color(0xFF2E9E5B);
    if (device.isPending) return scheme.tertiary;
    return scheme.primary;
  }

  Widget _row(BuildContext context, String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 10),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 100,
          child: Text(
            label,
            style: Theme.of(context).textTheme.labelLarge,
          ),
        ),
        Expanded(child: Text(value)),
      ],
    ),
  );

  Future<void> _authorize(BuildContext context, String operation) async {
    final outcome = await requests.authorize(pcId: device.id, operation: operation);
    if (!context.mounted) return;
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(outcome.succeeded ? 'Done' : 'Not completed'),
        content: Text(_outcomeMessage(outcome, operation)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  String _outcomeMessage(AuthorizationOutcome outcome, String operation) {
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

  Future<void> _revoke(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Revoke access?'),
        content: Text(
          '${device.name} will no longer be able to receive authorization requests.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Revoke'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final ok = await devices.revoke(device.id);
    if (!context.mounted) return;
    if (ok) {
      Navigator.of(context).pop();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(devices.error ?? 'Revoke failed.')),
      );
    }
  }

  Future<void> _delete(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove this PC?'),
        content: Text(
          '${device.name} will be deleted along with its history. '
          'This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final ok = await devices.remove(device.id);
    if (!context.mounted) return;
    if (ok) {
      Navigator.of(context).pop();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(devices.error ?? 'Could not remove the PC.')),
      );
    }
  }
}
