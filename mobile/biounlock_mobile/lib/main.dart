import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'app.dart';
import 'services/passkey_service.dart';
import 'services/session_store.dart';
import 'state/app_state.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final appState = AppState(
    store: SecureSessionStore(storage: const FlutterSecureStorage()),
    passkeyService: PlatformPasskeyService(),
  );
  appState.init();
  runApp(BioUnlockApp(appState: appState));
}
