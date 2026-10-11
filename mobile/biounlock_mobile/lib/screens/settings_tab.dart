import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';

class SettingsTab extends StatelessWidget {
  const SettingsTab({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final info = state.serverInfo;
    return Scaffold(
      body: ListView(
        children: [
          const ListTile(
            leading: Icon(Icons.dns),
            title: Text('Server'),
          ),
          ListTile(
            leading: const SizedBox(width: 24),
            title: const Text('URL'),
            subtitle: Text(state.serverUrl ?? '—'),
            trailing: const Icon(Icons.edit_outlined),
            onTap: () => _confirmChangeServer(context, prefill: state.serverUrl),
          ),
          if (info != null) ...[
            ListTile(
              leading: const SizedBox(width: 24),
              title: const Text('Version'),
              subtitle: Text('${info.name} ${info.version} (${info.environment})'),
            ),
            ListTile(
              leading: const SizedBox(width: 24),
              title: const Text('Relying party ID'),
              subtitle: Text(info.rpId),
            ),
            ListTile(
              leading: const SizedBox(width: 24),
              title: const Text('Signing key fingerprint'),
              subtitle: SelectableText(info.signingKeyFingerprint),
            ),
          ],
          const Divider(),
          ListTile(
            leading: const Icon(Icons.swap_horiz),
            title: const Text('Change server'),
            subtitle: const Text('Enter a new API base URL'),
            onTap: () => _confirmChangeServer(context),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmChangeServer(
    BuildContext context, {
    String? prefill,
  }) async {
    final controller = TextEditingController(text: prefill ?? '');
    final save = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Server URL'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: const InputDecoration(
            hintText: 'http://192.168.1.10:8000',
            border: OutlineInputBorder(),
          ),
          onSubmitted: (value) => Navigator.of(context).pop(value),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (save == null || !context.mounted) return;
    final ok = await context.read<AppState>().configureServer(save);
    if (!context.mounted) return;
    if (ok) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Server updated.')));
    }
  }
}