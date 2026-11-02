import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/misc.dart';
import '../state/passkeys_controller.dart';
import '../theme.dart';
import '../widgets/empty_state.dart';
import '../widgets/glass_card.dart';
import '../widgets/section_header.dart';

class PasskeysTab extends StatelessWidget {
  const PasskeysTab({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<PasskeysController>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: RefreshIndicator(
        onRefresh: controller.load,
        child: _buildBody(context, controller),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: controller.busy ? null : () => _add(context),
        icon: const Icon(Icons.add_rounded),
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
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 24, 16, 112),
        children: [
          EmptyState(
            icon: Icons.fingerprint_rounded,
            title: 'No passkeys yet',
            message:
                'Add a passkey to authorize your PCs with your fingerprint or '
                'face.',
            action: FilledButton.icon(
              onPressed: () => _add(context),
              icon: const Icon(Icons.add_rounded),
              label: const Text('Add a passkey'),
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
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 112),
      children: [
        SectionHeader(
          title: 'Your passkeys',
          caption: '${controller.credentials.length}',
        ),
        for (final credential in controller.credentials) ...[
          const SizedBox(height: 12),
          _PasskeyCard(credential, controller: controller),
        ],
      ],
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
          ok
              ? 'Passkey added.'
              : controller.error ?? 'Passkey registration failed.',
        ),
      ),
    );
  }
}

class _PasskeyCard extends StatelessWidget {
  const _PasskeyCard(this.credential, {required this.controller});

  final PasskeyCredential credential;
  final PasskeysController controller;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    return GlassCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
      child: Row(
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: scheme.primary.withValues(alpha: 0.12),
              border: Border.all(color: scheme.primary.withValues(alpha: 0.25)),
            ),
            child: Icon(Icons.fingerprint_rounded, color: scheme.primary),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  credential.name ?? 'Passkey',
                  style: context.texts.titleMedium,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  'Added ${_formatDate(credential.createdAt)}',
                  style: context.texts.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline_rounded),
            tooltip: 'Remove passkey',
            color: scheme.error,
            onPressed: controller.busy
                ? null
                : () => _delete(context, credential.id),
          ),
        ],
      ),
    );
  }

  Future<void> _delete(BuildContext context, String id) async {
    final ok = await controller.deletePasskey(id);
    if (!context.mounted || ok) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(controller.error ?? 'Could not remove passkey.')),
    );
  }
}

String _formatDate(DateTime value) {
  final local = value.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${local.year}-${two(local.month)}-${two(local.day)}';
}
