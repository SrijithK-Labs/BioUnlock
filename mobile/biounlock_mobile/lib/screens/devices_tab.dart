import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/device.dart';
import '../state/devices_controller.dart';
import '../state/requests_controller.dart';
import '../theme.dart';
import '../widgets/device_status.dart';
import '../widgets/empty_state.dart';
import '../widgets/glass_card.dart';
import '../widgets/section_header.dart';
import '../widgets/status_pill.dart';
import 'device_detail_screen.dart';
import 'scan_pairing_screen.dart';

class DevicesTab extends StatelessWidget {
  const DevicesTab({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<DevicesController>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: RefreshIndicator(
        onRefresh: controller.load,
        child: _buildBody(context, controller),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _scan(context),
        icon: const Icon(Icons.qr_code_scanner_rounded),
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
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 24, 16, 112),
        children: [
          EmptyState(
            icon: Icons.desktop_windows_rounded,
            title: 'No PCs yet',
            message:
                'Run the BioUnlock agent on your PC and scan its QR code to '
                'link it to this phone.',
            action: FilledButton.icon(
              onPressed: () => _scan(context),
              icon: const Icon(Icons.qr_code_scanner_rounded),
              label: const Text('Pair a PC'),
            ),
          ),
          if (controller.error != null) ...[
            const SizedBox(height: 12),
            Text(
              controller.error!,
              textAlign: TextAlign.center,
              style: context.texts.bodySmall?.copyWith(
                color: context.scheme.error,
              ),
            ),
          ],
        ],
      );
    }

    final devices = controller.devices;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 112),
      children: [
        _Overview(devices: devices),
        const SizedBox(height: 26),
        SectionHeader(title: 'Your PCs', caption: '${devices.length}'),
        for (final device in devices) ...[
          const SizedBox(height: 14),
          _PcCard(
            device: device,
            onOpen: () => _open(context, controller, device),
            onDelete: device.isRevoked
                ? () => _confirmDelete(context, controller, device)
                : null,
          ),
        ],
      ],
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

class _Overview extends StatelessWidget {
  const _Overview({required this.devices});

  final List<Device> devices;

  @override
  Widget build(BuildContext context) {
    final online = devices.where((d) => d.isOnline && d.isActive).length;
    final pending = devices.where((d) => d.isPending).length;
    return GlassCard(
      accent: context.scheme.primary,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
      child: Row(
        children: [
          _Stat(value: '${devices.length}', label: 'PCs'),
          const _StatDivider(),
          _Stat(
            value: '$online',
            label: 'Online',
            tint: context.tokens.success,
          ),
          const _StatDivider(),
          _Stat(
            value: '$pending',
            label: 'Pending',
            tint: context.scheme.tertiary,
          ),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.label, this.tint});

  final String value;
  final String label;
  final Color? tint;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    return Expanded(
      child: Column(
        children: [
          Text(
            value,
            style: context.texts.headlineSmall?.copyWith(
              color: tint ?? scheme.onSurface,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: context.texts.bodySmall?.copyWith(
              color: scheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatDivider extends StatelessWidget {
  const _StatDivider();

  @override
  Widget build(BuildContext context) =>
      Container(width: 1, height: 34, color: context.scheme.outlineVariant);
}

class _PcCard extends StatelessWidget {
  const _PcCard({required this.device, required this.onOpen, this.onDelete});

  final Device device;
  final VoidCallback onOpen;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    final status = deviceStatusOf(context, device);

    return GlassCard(
      onTap: onOpen,
      accent: status.color,
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          _DeviceIcon(device: device, size: 48),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  device.name,
                  style: context.texts.titleMedium,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 7),
                Row(
                  children: [
                    StatusPill(label: status.label, color: status.color),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        device.platform,
                        style: context.texts.bodySmall?.copyWith(
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
          const SizedBox(width: 6),
          if (onDelete != null)
            IconButton(
              icon: const Icon(Icons.delete_outline_rounded),
              tooltip: 'Remove PC',
              color: scheme.error,
              onPressed: onDelete,
            )
          else
            Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant),
        ],
      ),
    );
  }
}

class _DeviceIcon extends StatelessWidget {
  const _DeviceIcon({required this.device, required this.size});

  final Device device;
  final double size;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    final status = deviceStatusOf(context, device);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: status.color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(size * 0.32),
        border: Border.all(color: status.color.withValues(alpha: 0.28)),
      ),
      child: Icon(
        deviceIconOf(device),
        size: size * 0.5,
        color: device.isOnline ? status.color : scheme.onSurfaceVariant,
      ),
    );
  }
}
