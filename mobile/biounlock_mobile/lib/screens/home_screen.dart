import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api_client.dart';
import '../state/app_state.dart';
import '../state/devices_controller.dart';
import '../state/passkeys_controller.dart';
import '../state/requests_controller.dart';
import 'activity_tab.dart';
import 'devices_tab.dart';
import 'passkeys_tab.dart';
import 'settings_tab.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    ApiClient client() => context.read<AppState>().api!;

    return MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) =>
              DevicesController(api: appState.api!, apiProvider: client)
                ..load(),
        ),
        ChangeNotifierProvider(
          create: (_) => PasskeysController(
            api: appState.api!,
            passkeys: appState.passkeys,
            apiProvider: client,
          )..load(),
        ),
        ChangeNotifierProvider(
          create: (_) =>
              RequestsController(api: appState.api!, passkeys: appState.passkeys, apiProvider: client)
                ..load(),
        ),
      ],
      child: Scaffold(
        appBar: AppBar(
          titleSpacing: 16,
          title: Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary,
                  borderRadius: BorderRadius.circular(9),
                ),
                child: Icon(
                  Icons.fingerprint,
                  size: 20,
                  color: Theme.of(context).colorScheme.onPrimary,
                ),
              ),
              const SizedBox(width: 10),
              const Text('BioUnlock'),
            ],
          ),
        ),
        body: IndexedStack(
          index: _index,
          children: const [
            DevicesTab(),
            PasskeysTab(),
            ActivityTab(),
            SettingsTab(),
          ],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: (i) => setState(() => _index = i),
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.computer),
              label: 'PCs',
            ),
            NavigationDestination(
              icon: Icon(Icons.key),
              label: 'Passkeys',
            ),
            NavigationDestination(
              icon: Icon(Icons.history),
              label: 'Activity',
            ),
            NavigationDestination(
              icon: Icon(Icons.settings),
              label: 'Settings',
            ),
          ],
        ),
      ),
    );
  }
}
