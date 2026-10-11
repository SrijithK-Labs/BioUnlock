import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/misc.dart';
import '../state/app_state.dart';
import '../state/requests_controller.dart';

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
      context.read<AppState>().api!.securityEvents();

  Future<void> _refresh() async {
    setState(() => _events = _load());
    await Future.wait([
      _events,
      context.read<RequestsController>().load(),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final requests = context.watch<RequestsController>();
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          children: [
            const _SectionHeader('Recent authorization requests'),
            if (requests.requests.isEmpty)
              const ListTile(title: Text('No requests yet.'))
            else
              ...requests.requests.take(20).map(
                (r) => ListTile(
                  leading: Icon(_statusIcon(r.status)),
                  title: Text(r.pcName ?? r.pcId),
                  subtitle: Text(
                    '${r.operation} · ${r.createdAt.toLocal().toString().split('.').first}',
                  ),
                  trailing: Text(r.status),
                ),
              ),
            const Divider(),
            const _SectionHeader('Security events'),
            FutureBuilder<List<SecurityEvent>>(
              future: _events,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                if (snapshot.hasError) {
                  return ListTile(
                    title: Text('Could not load events: ${snapshot.error}'),
                  );
                }
                final events = snapshot.data ?? const [];
                if (events.isEmpty) {
                  return const ListTile(title: Text('No events yet.'));
                }
                return Column(
                  children: events
                      .map(
                        (e) => ListTile(
                          leading: const Icon(Icons.shield_outlined),
                          title: Text(e.eventType),
                          subtitle: Text(e.detail),
                          trailing: Text(
                            e.createdAt
                                .toLocal()
                                .toString()
                                .split('.')
                                .first,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      )
                      .toList(),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  IconData _statusIcon(String status) => switch (status) {
    'verified' => Icons.verified_user,
    'rejected' => Icons.gpp_bad,
    'expired' => Icons.timer_off,
    _ => Icons.hourglass_empty,
  };
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.title);

  final String title;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
    child: Text(title, style: Theme.of(context).textTheme.titleMedium),
  );
}
