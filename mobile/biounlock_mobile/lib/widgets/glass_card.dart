import 'package:flutter/material.dart';

import '../theme.dart';

/// A flat, bordered surface used for the main content cards. It is backed by a
/// [Material] so child [ListTile]s and ink splashes render correctly.
class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.onTap,
    this.padding = const EdgeInsets.all(16),
    this.radius = 16,
    this.accent,
  });

  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsetsGeometry padding;
  final double radius;

  /// When set, the card border is tinted with this colour (e.g. a status).
  final Color? accent;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(radius),
      side: BorderSide(
        color: accent?.withValues(alpha: 0.5) ?? scheme.outlineVariant,
      ),
    );

    return Material(
      color: scheme.surfaceContainerHigh,
      shape: shape,
      clipBehavior: Clip.antiAlias,
      child: onTap == null
          ? Padding(padding: padding, child: child)
          : InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(radius),
              child: Padding(padding: padding, child: child),
            ),
    );
  }
}
