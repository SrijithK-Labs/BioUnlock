import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/auth_request.dart';
import '../models/misc.dart';
import '../state/app_state.dart';
import '../state/requests_controller.dart';
import '../theme.dart';
import '../widgets/glass_card.dart';
import '../widgets/section_header.dart';
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

  Future<List<SecurityEvent>> _load() => context
      .read<AppState>()
      .api!
      .securityEvents(limit: _historyLimit, days: _historyDays);

  Future<void> _refresh() async {
    setState(() => _events = _load());
    await Future.wait([_events, context.read<RequestsController>().load()]);
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
      backgroundColor: Colors.transparent,
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            SectionHeader(
              title: 'Recent requests',
              caption: 'Last $_historyDays days',
            ),
            if (recentRequests.isEmpty)
              const _EmptyCard(
                icon: Icons.hourglass_empty_rounded,
                message: 'No authorization requests in this period.',
              )
            else
              GlassCard(
                padding: EdgeInsets.zero,
                child: Column(
                  children: [
                    for (var i = 0; i < recentRequests.length; i++) ...[
                      if (i > 0) const Divider(height: 1),
                      _RequestTile(recentRequests[i]),
                    ],
                  ],
                ),
              ),
            const SizedBox(height: 28),
            SectionHeader(
              title: 'Security events',
              caption: 'Last $_historyDays days',
            ),
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
                  return _EmptyCard(
                    icon: Icons.error_outline_rounded,
                    message: 'Could not load events: ${snapshot.error}',
                  );
                }
                final events = (snapshot.data ?? const <SecurityEvent>[])
                    .where((e) => _isRecent(e.createdAt))
                    .take(_historyLimit)
                    .toList();
                if (events.isEmpty) {
                  return const _EmptyCard(
                    icon: Icons.shield_outlined,
                    message: 'No security events in this period.',
                  );
                }
                return GlassCard(
                  padding: EdgeInsets.zero,
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
    final scheme = context.scheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
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
                  style: context.texts.titleSmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  '${_operationLabel(request.operation)} · ${_formatTime(request.createdAt)}',
                  style: context.texts.bodySmall?.copyWith(
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
    final scheme = context.scheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
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
                  style: context.texts.titleSmall,
                ),
                if (event.detail.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    event.detail,
                    style: context.texts.bodySmall?.copyWith(
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
            style: context.texts.bodySmall?.copyWith(
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
      width: 42,
      height: 42,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        shape: BoxShape.circle,
        border: Border.all(color: color.withValues(alpha: 0.22)),
      ),
      child: Icon(icon, size: 20, color: color),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = context.scheme;
    return GlassCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      child: Row(
        children: [
          Icon(icon, size: 20, color: scheme.onSurfaceVariant),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              message,
              style: context.texts.bodyMedium?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

IconData _statusIcon(String status) => switch (status) {
  'verified' => Icons.verified_user_rounded,
  'rejected' => Icons.gpp_bad_rounded,
  'expired' => Icons.timer_off_rounded,
  _ => Icons.hourglass_empty_rounded,
};

Color _statusColor(ColorScheme scheme, String status) => switch (status) {
  'verified' => const Color(0xFF34D399),
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
    .map(
      (word) =>
          word.isEmpty ? word : '${word[0].toUpperCase()}${word.substring(1)}',
    )
    .join(' ');

String _formatTime(DateTime value) {
  final local = value.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${local.year}-${two(local.month)}-${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}';
}
