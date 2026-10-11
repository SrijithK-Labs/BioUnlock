import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/device.dart';
import '../state/devices_controller.dart';
import '../state/requests_controller.dart';
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
          const SizedBox(height: 120),
          const Icon(Icons.computer, size: 72),
          const SizedBox(height: 12),
          const Center(
            child: Text(
              'No PCs yet.\nRun the BioUnlock agent on your PC and scan its QR code.',
              textAlign: TextAlign.center,
            ),
          ),
          if (controller.error != null) ...[
            const SizedBox(height: 12),
            Center(
              child: Text(
                controller.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ],
      );
    }
    return ListView.builder(
      itemCount: controller.devices.length,
      itemBuilder: (context, i) {
        final device = controller.devices[i];
        return ListTile(
          leading: Icon(
            device.isOnline ? Icons.desktop_windows : Icons.desktop_access_disabled,
            color: device.isOnline ? Colors.green : null,
          ),
          title: Text(device.name),
          subtitle: Text(_subtitle(device)),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => DeviceDetailScreen(
                device: device,
                devices: controller,
                requests: context.read<RequestsController>(),
              ),
            ),
          ),
        );
      },
    );
  }

  String _subtitle(Device device) {
    final status = switch (device.status) {
      'active' => device.isOnline ? 'Online' : 'Paired',
      'pending' => 'Awaiting pairing',
      'revoked' => 'Revoked',
      _ => device.status,
    };
    return '${device.platform} · $status';
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
}
