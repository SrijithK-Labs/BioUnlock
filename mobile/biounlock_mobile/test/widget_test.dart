import 'package:biounlock_mobile/app.dart';
import 'package:biounlock_mobile/services/session_store.dart';
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
      store: InMemorySessionStore(),
      passkeyService: FakePasskeyService(),
      httpClient: MockClient((_) async => http.Response('{}', 404)),
    );
    await state.init();

    await tester.pumpWidget(BioUnlockApp(appState: state));
    await tester.pumpAndSettle();

    expect(find.text('BioUnlock setup'), findsOneWidget);
    expect(find.text('Connect'), findsOneWidget);
  });
}
