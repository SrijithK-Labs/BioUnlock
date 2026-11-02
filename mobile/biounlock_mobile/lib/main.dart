import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'app.dart';
import 'services/api_token_store.dart';
import 'services/enrollment_token_store.dart';
import 'services/passkey_service.dart';
import 'services/preferences_store.dart';
import 'services/server_url_store.dart';
import 'state/app_state.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  const storage = FlutterSecureStorage();
  final appState = AppState(
    store: SecureServerUrlStore(storage: storage),
    tokenStore: SecureApiTokenStore(storage: storage),
    enrollmentTokenStore: SecureEnrollmentTokenStore(storage: storage),
    preferences: SecurePreferencesStore(storage: storage),
    passkeyService: PlatformPasskeyService(),
  );
  appState.init();
  runApp(BioUnlockApp(appState: appState));
}
