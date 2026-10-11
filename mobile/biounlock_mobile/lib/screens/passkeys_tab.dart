import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/passkeys_controller.dart';

class PasskeysTab extends StatelessWidget {
  const PasskeysTab({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<PasskeysController>();
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: controller.load,
        child: _buildBody(context, controller),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: controller.busy ? null : () => _add(context),
        icon: const Icon(Icons.add),
        label: const Text('Add passkey'),
      ),
    );
  }

  Widget _buildBody(BuildContext context, PasskeysController controller) {
    if (controller.busy && controller.credentials.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (controller.credentials.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 120),
          const Icon(Icons.key, size: 72),
          const SizedBox(height: 12),
          const Center(
            child: Text(
              'No passkeys yet.\nAdd a passkey to authorize your PCs with biometrics.',
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
      itemCount: controller.credentials.length,
      itemBuilder: (context, i) {
        final credential = controller.credentials[i];
        return ListTile(
          leading: const Icon(Icons.key),
          title: Text(credential.name ?? 'Passkey'),
          subtitle: Text(
            'Added ${credential.createdAt.toLocal().toString().split('.').first}',
          ),
          trailing: IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: 'Remove passkey',
            onPressed: controller.busy
                ? null
                : () => _delete(context, controller, credential.id),
          ),
        );
      },
    );
  }

  Future<void> _add(BuildContext context) async {
    final controller = context.read<PasskeysController>();
    final nameController = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Name this passkey'),
        content: TextField(
          controller: nameController,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: 'e.g. Pixel 7a fingerprint',
          ),
          onSubmitted: (value) => Navigator.of(context).pop(value),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(nameController.text),
            child: const Text('Continue'),
          ),
        ],
      ),
    );
    if (name == null) return;
    final ok = await controller.registerPasskey(
      name: name.trim().isEmpty ? null : name.trim(),
    );
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok ? 'Passkey added.' : controller.error ?? 'Passkey registration failed.',
        ),
      ),
    );
  }

  Future<void> _delete(
    BuildContext context,
    PasskeysController controller,
    String id,
  ) async {
    final ok = await controller.deletePasskey(id);
    if (!context.mounted || ok) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(controller.error ?? 'Could not remove passkey.')),
    );
  }
}
