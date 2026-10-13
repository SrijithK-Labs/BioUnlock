import 'package:flutter/material.dart';

import '../models/device.dart';
import '../state/devices_controller.dart';
import '../state/requests_controller.dart';
import '../theme.dart';
import '../widgets/action_button.dart';
import '../widgets/authorization.dart';
import '../widgets/device_status.dart';
import '../widgets/glass_card.dart';
import '../widgets/section_header.dart';
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
            const SizedBox(height: 18),
            _actions(context),
            const SizedBox(height: 26),
            const SectionHeader(title: 'Details'),
            _details(context),
            const SizedBox(height: 26),
            const SectionHeader(title: 'Danger zone'),
            _dangerZone(context),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext context) {
    final scheme = context.scheme;
    final status = deviceStatusOf(context, device);
    return GlassCard(
      accent: status.color,
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          Container(
            width: 62,
            height: 62,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  status.color.withValues(alpha: 0.26),
                  status.color.withValues(alpha: 0.08),
                ],
              ),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: status.color.withValues(alpha: 0.3)),
            ),
            child: Icon(
              deviceIconOf(device),
              size: 30,
              color: device.isOnline ? status.color : scheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(device.name, style: context.texts.titleLarge),
                const SizedBox(height: 8),
                StatusPill(label: status.label, color: status.color),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _actions(BuildContext context) {
    final scheme = context.scheme;
    final active = device.isActive;
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(18, 22, 18, 20),
      child: Column(
        children: [
          if (requests.stage != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(
                    height: 15,
                    width: 15,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: 10),
                  Flexible(
                    child: Text(
                      requests.stage!,
                      textAlign: TextAlign.center,
                      style: context.texts.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ],
              ),
            )
          else if (requests.error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Text(
                requests.error!,
                textAlign: TextAlign.center,
                style: context.texts.bodySmall?.copyWith(color: scheme.error),
              ),
            ),
          ActionButton(
            label: 'Unlock this PC',
            icon: Icons.lock_open_rounded,
            busy: requests.busy,
            enabled: active,
            onPressed: () => _authorize(context, 'remote_unlock'),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: (!active || requests.busy)
                ? null
                : () => _authorize(context, 'remote_lock'),
            icon: const Icon(Icons.lock_outline_rounded, size: 20),
            label: const Text('Lock this PC'),
          ),
        ],
      ),
    );
  }

  Widget _details(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 6),
      child: Column(
        children: [
          _row(context, 'Platform', device.platform),
          const Divider(height: 1),
          _row(
            context,
            'Last seen',
            device.lastSeenAt?.toLocal().toString() ?? 'Never',
          ),
          if (device.pairedAt != null) ...[
            const Divider(height: 1),
            _row(context, 'Paired at', device.pairedAt!.toLocal().toString()),
          ],
        ],
      ),
    );
  }

  Widget _dangerZone(BuildContext context) {
    final scheme = context.scheme;
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            device.isRevoked
                ? 'This PC is revoked and can be removed permanently.'
                : 'Revoking blocks this PC from receiving unlock requests.',
            style: context.texts.bodySmall?.copyWith(
              color: scheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 14),
          if (device.isRevoked)
            FilledButton.icon(
              onPressed: devices.busy ? null : () => _delete(context),
              icon: const Icon(Icons.delete_outline_rounded),
              label: const Text('Delete this PC'),
              style: FilledButton.styleFrom(
                backgroundColor: scheme.error,
                foregroundColor: scheme.onError,
              ),
            )
          else
            OutlinedButton.icon(
              onPressed: devices.busy ? null : () => _revoke(context),
              icon: const Icon(Icons.block_rounded),
              label: const Text('Revoke access'),
              style: OutlinedButton.styleFrom(foregroundColor: scheme.error),
            ),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 14),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 96,
          child: Text(
            label,
            style: context.texts.labelLarge?.copyWith(
              color: context.scheme.onSurfaceVariant,
            ),
          ),
        ),
        Expanded(child: Text(value)),
      ],
    ),
  );

  Future<void> _authorize(BuildContext context, String operation) async {
    final outcome = await requests.authorize(
      pcId: device.id,
      operation: operation,
    );
    if (!context.mounted) return;
    await showAuthorizationResult(context, outcome, operation);
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
