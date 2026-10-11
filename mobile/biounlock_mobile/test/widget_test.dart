import 'package:biounlock_mobile/app.dart';
import 'package:biounlock_mobile/services/server_url_store.dart';
import 'package:biounlock_mobile/state/app_state.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'fakes.dart';

void main() {
  testWidgets('shows setup screen when no server is configured', (
    WidgetTester tester,
  ) async {
    final state = AppState(
      store: InMemoryServerUrlStore(),
      passkeyService: FakePasskeyService(),
      httpClient: MockClient((_) async => http.Response('{}', 404)),
    );
    await state.init();

    await tester.pumpWidget(BioUnlockApp(appState: state));
    await tester.pumpAndSettle();

    expect(find.text('BioUnlock setup'), findsOneWidget);
    expect(find.text('Connect'), findsOneWidget);
  });

  testWidgets('shows home tabs when a server is configured', (
    WidgetTester tester,
  ) async {
    final state = AppState(
      store: InMemoryServerUrlStore(serverUrl: 'https://example.com'),
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
        'GET /api/v1/devices': (_) => ok([deviceJson()]),
        'GET /api/v1/webauthn/credentials': (_) => ok([]),
        'GET /api/v1/requests': (_) => ok([]),
        'GET /api/v1/security-events': (_) => ok([]),
      }),
    );
    await state.init();

    await tester.pumpWidget(BioUnlockApp(appState: state));
    await tester.pumpAndSettle();

    expect(state.isConfigured, isTrue);
    expect(find.text('BioUnlock'), findsOneWidget);
    expect(find.text('Passkeys'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
  });
}