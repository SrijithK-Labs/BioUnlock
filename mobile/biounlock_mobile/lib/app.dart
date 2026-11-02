import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/home_screen.dart';
import 'screens/setup_screen.dart';
import 'state/app_state.dart';
import 'theme.dart';

class BioUnlockApp extends StatelessWidget {
  const BioUnlockApp({super.key, required this.appState});

  final AppState appState;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<AppState>.value(
      value: appState,
      child: Consumer<AppState>(
        builder: (context, state, _) => MaterialApp(
          title: 'BioUnlock',
          debugShowCheckedModeBanner: false,
          theme: AppTheme.light(),
          darkTheme: AppTheme.dark(),
          themeMode: state.themeMode,
          home: const _RootGate(),
        ),
      ),
    );
  }
}

class _RootGate extends StatelessWidget {
  const _RootGate();

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (!state.initialized) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!state.isConfigured) {
      return const SetupScreen();
    }
    return const HomeScreen();
  }
}
