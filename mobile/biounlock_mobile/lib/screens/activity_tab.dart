import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/auth_request.dart';
import '../models/misc.dart';
import '../state/app_state.dart';
import '../state/requests_controller.dart';
import '../widgets/empty_state.dart';
import '../widgets/status_pill.dart';

/// Activity keeps a short, bounded history: the last 30 days, at most 50 items.
const int _historyDays = 30;
const int _historyLimit = 50;

class ActivityTab extends StatefulWidget {
  const ActivityTab({super.key});

  @override
  State<ActivityTab> createState() => _ActivityTabState();
}

class _ActivityTabState extends State<ActivityTab> {
  late Future<List<SecurityEvent>> _events;

  @override
  void initState() {
    super.initState();
    _events = _load();
  }

  Future<List<SecurityEvent>> _load() =>
      context.read<AppState>().api!.securityEvents(
        limit: _historyLimit,
        days: _historyDays,
      );

  Future<void> _refresh() async {
    setState(() => _events = _load());
    await Future.wait([
      _events,
      context.read<RequestsController>().load(),
    ]);
  }

  static bool _isRecent(DateTime value) {
    final cutoff = DateTime.now().subtract(const Duration(days: _historyDays));
    return value.isAfter(cutoff);
  }

  @override
  Widget build(BuildContext context) {
    final requests = context.watch<RequestsController>();
    final recentRequests = requests.requests
        .where((r) => _isRecent(r.createdAt))
        .take(_historyLimit)
        .toList();

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            const _SectionHeader(
              'Recent requests',
              subtitle: 'Last $_historyDays days',
            ),
            const SizedBox(height: 8),
            if (recentRequests.isEmpty)
              const _EmptyCard('No authorization requests in this period.')
            else
              Card(
                child: Column(
                  children: [
                    for (var i = 0; i < recentRequests.length; i++) ...[
                      if (i > 0) const Divider(height: 1),
                      _RequestTile(recentRequests[i]),
                    ],
                  ],
                ),
              ),
            const SizedBox(height: 24),
            const _SectionHeader(
              'Security events',
              subtitle: 'Last $_historyDays days',
            ),
            const SizedBox(height: 8),
            FutureBuilder<List<SecurityEvent>>(
              future: _events,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting &&
                    !snapshot.hasData) {
                  return const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                if (snapshot.hasError) {
                  return _EmptyCard('Could not load events: ${snapshot.error}');
                }
                final events = (snapshot.data ?? const <SecurityEvent>[])
                    .where((e) => _isRecent(e.createdAt))
                    .take(_historyLimit)
                    .toList();
                if (events.isEmpty) {
                  return const _EmptyCard('No security events in this period.');
                }
                return Card(
                  child: Column(
                    children: [
                      for (var i = 0; i < events.length; i++) ...[
                        if (i > 0) const Divider(height: 1),
                        _EventTile(events[i]),
                      ],
                    ],
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _RequestTile extends StatelessWidget {
  const _RequestTile(this.request);

  final AuthRequest request;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          _IconBadge(
            icon: _statusIcon(request.status),
            color: _statusColor(scheme, request.status),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  request.pcName ?? request.pcId,
                  style: theme.textTheme.titleSmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  '${_operationLabel(request.operation)} · ${_formatTime(request.createdAt)}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          StatusPill(
            label: request.status,
            color: _statusColor(scheme, request.status),
          ),
        ],
      ),
    );
  }
}

class _EventTile extends StatelessWidget {
  const _EventTile(this.event);

  final SecurityEvent event;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _IconBadge(icon: Icons.shield_outlined, color: scheme.primary),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _eventLabel(event.eventType),
                  style: theme.textTheme.titleSmall,
                ),
                if (event.detail.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    event.detail,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            _formatTime(event.createdAt),
            style: theme.textTheme.bodySmall?.copyWith(
              color: scheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _IconBadge extends StatelessWidget {
  const _IconBadge({required this.icon, required this.color});

  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        shape: BoxShape.circle,
      ),
      child: Icon(icon, size: 20, color: color),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.title, {this.subtitle});

  final String title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.baseline,
      textBaseline: TextBaseline.alphabetic,
      children: [
        Text(title, style: theme.textTheme.titleMedium),
        if (subtitle != null) ...[
          const SizedBox(width: 8),
          Text(
            subtitle!,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ],
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: EmptyState(
          icon: Icons.history,
          title: message,
        ),
      ),
    );
  }
}

IconData _statusIcon(String status) => switch (status) {
  'verified' => Icons.verified_user,
  'rejected' => Icons.gpp_bad,
  'expired' => Icons.timer_off,
  _ => Icons.hourglass_empty,
};

Color _statusColor(ColorScheme scheme, String status) => switch (status) {
  'verified' => const Color(0xFF2E9E5B),
  'rejected' => scheme.error,
  'expired' => scheme.outline,
  _ => scheme.tertiary,
};

String _operationLabel(String operation) => switch (operation) {
  'remote_lock' => 'Lock',
  'remote_unlock' => 'Unlock',
  _ => operation,
};

String _eventLabel(String eventType) => eventType
    .split('_')
    .map((word) => word.isEmpty ? word : '${word[0].toUpperCase()}${word.substring(1)}')
    .join(' ');

String _formatTime(DateTime value) {
  final local = value.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${local.year}-${two(local.month)}-${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}';
}
