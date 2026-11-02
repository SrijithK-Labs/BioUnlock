import 'package:flutter/material.dart';

import '../theme.dart';

/// A small monospace-style eyebrow label used to title a group of content.
class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.title,
    this.caption,
    this.trailing,
  });

  final String title;
  final String? caption;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 4, 4, 10),
      child: Row(
        children: [
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(
                  title,
                  style: context.texts.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (caption != null) ...[
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      caption!,
                      overflow: TextOverflow.ellipsis,
                      style: context.texts.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}
