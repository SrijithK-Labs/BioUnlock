import 'package:flutter/material.dart';

import '../theme.dart';

/// A solid, full-width primary action button.
class ActionButton extends StatelessWidget {
  const ActionButton({
    super.key,
    required this.label,
    required this.icon,
    required this.onPressed,
    this.busy = false,
    this.enabled = true,
    this.height = 52,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final bool busy;
  final bool enabled;
  final double height;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    final active = enabled && !busy && onPressed != null;
    return SizedBox(
      height: height,
      child: FilledButton(
        onPressed: active ? onPressed : null,
        style: FilledButton.styleFrom(
          minimumSize: Size.fromHeight(height),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (busy)
              SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2.4,
                  color: scheme.onPrimary,
                ),
              )
            else
              Icon(icon, size: 20),
            const SizedBox(width: 10),
            Text(label),
          ],
        ),
      ),
    );
  }
}
