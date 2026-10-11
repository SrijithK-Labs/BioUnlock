import 'package:flutter/material.dart';

import '../models/device.dart';
import '../state/devices_controller.dart';
import '../state/requests_controller.dart';

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
          padding: const EdgeInsets.all(16),
          children: [
            _row(context, 'Platform', device.platform),
            _row(context, 'Status', device.status),
            _row(
              context,
              'Last seen',
              device.lastSeenAt?.toLocal().toString() ?? 'Never',
            ),
            if (device.pairedAt != null)
              _row(context, 'Paired at', device.pairedAt!.toLocal().toString()),
            const Divider(height: 32),
            if (requests.error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  requests.error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            FilledButton.icon(
              onPressed: (!device.isActive || requests.busy)
                  ? null
                  : () => _authorize(context),
              icon: const Icon(Icons.lock_open),
              label: Text(requests.busy ? 'Authorizing…' : 'Authorize this PC'),
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
            const SizedBox(height: 24),
            OutlinedButton.icon(
              onPressed: device.isRevoked || devices.busy
                  ? null
                  : () => _revoke(context),
              icon: const Icon(Icons.block),
              label: const Text('Revoke access'),
              style: OutlinedButton.styleFrom(
                foregroundColor: Theme.of(context).colorScheme.error,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
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

  Future<void> _authorize(BuildContext context) async {
    final outcome = await requests.authorize(pcId: device.id);
    if (!context.mounted) return;
    final message = switch (outcome.status) {
      'verified' => 'PC verified the request. Access granted.',
      'rejected' => 'PC rejected the request.${outcome.request?.ackReason != null ? ' (${outcome.request!.ackReason})' : ''}',
      'expired' => 'The request expired before the PC responded.',
      _ => outcome.message ?? 'Authorization could not be completed.',
    };
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(outcome.succeeded ? 'Verified' : 'Not verified'),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
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
}
