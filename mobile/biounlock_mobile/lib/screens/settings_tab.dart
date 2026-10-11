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
            leading: Icon(Icons.account_circle),
            title: Text('Account'),
          ),
          ListTile(
            leading: const SizedBox(width: 24),
            title: const Text('Email'),
            subtitle: Text(state.session?.account.email ?? '—'),
          ),
          const Divider(),
          const ListTile(
            leading: Icon(Icons.dns),
            title: Text('Server'),
          ),
          ListTile(
            leading: const SizedBox(width: 24),
            title: const Text('URL'),
            subtitle: Text(state.serverUrl ?? '—'),
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
            onTap: () => _confirmChangeServer(context),
          ),
          ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('Sign out'),
            onTap: () => state.logout(),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmChangeServer(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Change server?'),
        content: const Text(
          'You will be signed out and asked for a new server address.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Change'),
          ),
        ],
      ),
    );
    if (confirmed == true && context.mounted) {
      await context.read<AppState>().resetServer();
    }
  }
}
