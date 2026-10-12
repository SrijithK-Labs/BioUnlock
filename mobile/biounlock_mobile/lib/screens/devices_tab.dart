import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/device.dart';
import '../state/devices_controller.dart';
import '../state/requests_controller.dart';
import '../widgets/empty_state.dart';
import '../widgets/status_pill.dart';
import 'device_detail_screen.dart';
import 'scan_pairing_screen.dart';

class DevicesTab extends StatelessWidget {
  const DevicesTab({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<DevicesController>();
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: controller.load,
        child: _buildBody(context, controller),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _scan(context),
        icon: const Icon(Icons.qr_code_scanner),
        label: const Text('Pair PC'),
      ),
    );
  }

  Widget _buildBody(BuildContext context, DevicesController controller) {
    if (controller.busy && controller.devices.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (controller.devices.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          EmptyState(
            icon: Icons.computer,
            title: 'No PCs yet',
            message:
                'Run the BioUnlock agent on your PC and scan its QR code to link it.',
            action: controller.error == null
                ? null
                : Text(
                    controller.error!,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
          ),
        ],
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
      itemCount: controller.devices.length,
      separatorBuilder: (_, _) => const SizedBox(height: 12),
      itemBuilder: (context, i) {
        final device = controller.devices[i];
        return _DeviceCard(
          device: device,
          onOpen: () => _open(context, controller, device),
          onDelete: device.isRevoked
              ? () => _confirmDelete(context, controller, device)
              : null,
        );
      },
    );
  }

  void _open(
    BuildContext context,
    DevicesController controller,
    Device device,
  ) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => DeviceDetailScreen(
          device: device,
          devices: controller,
          requests: context.read<RequestsController>(),
        ),
      ),
    );
  }

  Future<void> _scan(BuildContext context) async {
    final controller = context.read<DevicesController>();
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(builder: (_) => const ScanPairingScreen()),
    );
    if (code == null || !context.mounted) return;
    final device = await controller.confirmPairing(code);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          device != null
              ? 'Paired ${device.name}.'
              : controller.error ?? 'Pairing failed.',
        ),
      ),
    );
  }

  Future<void> _confirmDelete(
    BuildContext context,
    DevicesController controller,
    Device device,
  ) async {
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
    final ok = await controller.remove(device.id);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok ? 'PC removed.' : controller.error ?? 'Could not remove the PC.',
        ),
      ),
    );
  }
}

class _DeviceCard extends StatelessWidget {
  const _DeviceCard({
    required this.device,
    required this.onOpen,
    this.onDelete,
  });

  final Device device;
  final VoidCallback onOpen;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final status = _status(theme, device);

    return Card(
      child: InkWell(
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: scheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(
                  device.isOnline
                      ? Icons.desktop_windows
                      : Icons.desktop_access_disabled,
                  color: device.isOnline
                      ? scheme.primary
                      : scheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      device.name,
                      style: theme.textTheme.titleMedium,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        StatusPill(label: status.label, color: status.color),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            device.platform,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: scheme.onSurfaceVariant,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              if (onDelete != null)
                IconButton(
                  icon: const Icon(Icons.delete_outline),
                  tooltip: 'Remove PC',
                  color: scheme.error,
                  onPressed: onDelete,
                )
              else
                Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }

  _Status _status(ThemeData theme, Device device) {
    if (device.isRevoked) {
      return _Status('Revoked', theme.colorScheme.error);
    }
    if (device.isOnline) {
      return const _Status('Online', Color(0xFF2E9E5B));
    }
    if (device.isPending) {
      return _Status('Awaiting pairing', theme.colorScheme.tertiary);
    }
    return _Status('Paired', theme.colorScheme.primary);
  }
}

class _Status {
  const _Status(this.label, this.color);

  final String label;
  final Color color;
}
