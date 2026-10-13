import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/glass_card.dart';
import '../widgets/section_header.dart';

class SettingsTab extends StatelessWidget {
  const SettingsTab({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final info = state.serverInfo;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          _connectionCard(context, state),
          const SizedBox(height: 26),
          const SectionHeader(title: 'Appearance'),
          GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.brightness_6_outlined,
                      color: context.scheme.primary,
                    ),
                    const SizedBox(width: 12),
                    Text('Theme', style: context.texts.titleMedium),
                  ],
                ),
                const SizedBox(height: 14),
                SegmentedButton<ThemeMode>(
                  showSelectedIcon: false,
                  segments: const [
                    ButtonSegment(
                      value: ThemeMode.system,
                      label: Text('System'),
                    ),
                    ButtonSegment(value: ThemeMode.light, label: Text('Light')),
                    ButtonSegment(value: ThemeMode.dark, label: Text('Dark')),
                  ],
                  selected: {state.themeMode},
                  onSelectionChanged: (selection) =>
                      context.read<AppState>().setThemeMode(selection.first),
                ),
              ],
            ),
          ),
          const SizedBox(height: 26),
          const SectionHeader(title: 'Server'),
          GlassCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.link_rounded),
                  title: const Text('URL'),
                  subtitle: Text(state.serverUrl ?? '—'),
                  trailing: const Icon(Icons.edit_outlined),
                  onTap: () => _editServerUrl(context),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.key_rounded),
                  title: const Text('API key'),
                  subtitle: Text(
                    (state.apiToken ?? '').isEmpty ? 'Not set' : '••••••••',
                  ),
                  trailing: const Icon(Icons.edit_outlined),
                  onTap: () => _editApiKey(context),
                ),
              ],
            ),
          ),
          if (info != null) ...[
            const SizedBox(height: 26),
            const SectionHeader(title: 'About'),
            GlassCard(
              padding: EdgeInsets.zero,
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
                    leading: const Icon(Icons.verified_user_outlined),
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

  Widget _connectionCard(BuildContext context, AppState state) {
    final scheme = context.scheme;
    final tokens = context.tokens;
    final connected = state.serverInfo != null;
    final color = connected ? tokens.success : tokens.warning;
    return GlassCard(
      accent: color,
      child: Row(
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: 0.16),
              border: Border.all(color: color.withValues(alpha: 0.3)),
            ),
            child: Icon(
              connected ? Icons.lock_rounded : Icons.wifi_off_rounded,
              color: color,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  connected ? 'Connected' : 'Server unreachable',
                  style: context.texts.titleMedium,
                ),
                const SizedBox(height: 4),
                Text(
                  state.serverUrl ?? 'No server configured',
                  style: context.texts.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _editServerUrl(BuildContext context) async {
    final state = context.read<AppState>();
    final controller = TextEditingController(text: state.serverUrl ?? '');
    final url = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Server URL'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: const InputDecoration(
            labelText: 'Server URL',
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
    if (url == null || !context.mounted) return;
    await _saveServer(context, () => state.configureServer(url));
  }

  Future<void> _editApiKey(BuildContext context) async {
    final state = context.read<AppState>();
    if (state.serverUrl == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Set a server URL first.')));
      return;
    }
    final controller = TextEditingController(text: state.apiToken ?? '');
    final token = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('API key'),
        content: TextField(
          controller: controller,
          autofocus: true,
          autocorrect: false,
          obscureText: true,
          decoration: const InputDecoration(
            labelText: 'API key',
            helperText: 'Set as BIO_API_TOKEN on your server',
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
    if (token == null || !context.mounted) return;
    await _saveServer(
      context,
      () => state.configureServer(state.serverUrl!, token: token),
    );
  }

  Future<void> _saveServer(
    BuildContext context,
    Future<bool> Function() run,
  ) async {
    final state = context.read<AppState>();
    final ok = await run();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          ok ? 'Server updated.' : (state.error ?? 'Could not connect.'),
        ),
      ),
    );
  }
}
