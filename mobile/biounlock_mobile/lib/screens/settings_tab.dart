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
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          const _SectionLabel('Appearance'),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.brightness_6_outlined),
                      const SizedBox(width: 12),
                      Text(
                        'Theme',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SegmentedButton<ThemeMode>(
                    segments: const [
                      ButtonSegment(
                        value: ThemeMode.system,
                        label: Text('System'),
                        icon: Icon(Icons.brightness_auto),
                      ),
                      ButtonSegment(
                        value: ThemeMode.light,
                        label: Text('Light'),
                        icon: Icon(Icons.light_mode),
                      ),
                      ButtonSegment(
                        value: ThemeMode.dark,
                        label: Text('Dark'),
                        icon: Icon(Icons.dark_mode),
                      ),
                    ],
                    selected: {state.themeMode},
                    onSelectionChanged: (selection) =>
                        context.read<AppState>().setThemeMode(selection.first),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          const _SectionLabel('Server'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.link),
                  title: const Text('URL'),
                  subtitle: Text(state.serverUrl ?? '—'),
                  trailing: const Icon(Icons.edit_outlined),
                  onTap: () =>
                      _confirmChangeServer(context, prefill: state.serverUrl),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.swap_horiz),
                  title: const Text('Change server'),
                  subtitle: const Text('Enter a new API base URL'),
                  onTap: () => _confirmChangeServer(context),
                ),
              ],
            ),
          ),
          if (info != null) ...[
            const SizedBox(height: 24),
            const _SectionLabel('About'),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.dns_outlined),
                    title: const Text('Server version'),
                    subtitle: Text(
                      '${info.name} ${info.version} (${info.environment})',
                    ),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const Icon(Icons.badge_outlined),
                    title: const Text('Relying party ID'),
                    subtitle: Text(info.rpId),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const Icon(Icons.vpn_key_outlined),
                    title: const Text('Signing key fingerprint'),
                    subtitle: SelectableText(info.signingKeyFingerprint),
                  ),
                ],
              ),
            ),
          ],
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

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.title);

  final String title;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(left: 4, bottom: 8),
    child: Text(
      title.toUpperCase(),
      style: Theme.of(context).textTheme.labelMedium?.copyWith(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        letterSpacing: 0.8,
      ),
    ),
  );
}
