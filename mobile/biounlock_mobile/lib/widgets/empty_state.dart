import 'package:flutter/material.dart';

import '../theme.dart';

/// Shared empty state used across the tabs: an icon badge, a title and an
/// optional supporting line and action.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.action,
  });

  final IconData icon;
  final String title;
  final String? message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHighest,
              shape: BoxShape.circle,
              border: Border.all(color: scheme.outlineVariant),
            ),
            child: Icon(icon, size: 36, color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 18),
          Text(
            title,
            style: context.texts.titleMedium,
            textAlign: TextAlign.center,
          ),
          if (message != null) ...[
            const SizedBox(height: 8),
            Text(
              message!,
              style: context.texts.bodyMedium?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
              textAlign: TextAlign.center,
            ),
          ],
          if (action != null) ...[const SizedBox(height: 20), action!],
        ],
      ),
    );
  }
}
