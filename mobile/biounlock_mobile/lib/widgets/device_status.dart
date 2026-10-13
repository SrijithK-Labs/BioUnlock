import 'package:flutter/material.dart';

import '../models/device.dart';
import '../theme.dart';

/// A human label + colour for a device's state, resolved against the theme.
class DeviceStatus {
  const DeviceStatus(this.label, this.color);

  final String label;
  final Color color;
}

DeviceStatus deviceStatusOf(BuildContext context, Device device) {
  final scheme = context.scheme;
  final tokens = context.tokens;
  if (device.isRevoked) return DeviceStatus('Revoked', scheme.error);
  if (device.isPending) {
    return DeviceStatus('Awaiting pairing', scheme.tertiary);
  }
  if (device.isOnline) return DeviceStatus('Online', tokens.success);
  return DeviceStatus('Paired', scheme.primary);
}

IconData deviceIconOf(Device device) => device.isOnline
    ? Icons.desktop_windows_rounded
    : Icons.desktop_access_disabled_rounded;
