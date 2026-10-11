import 'package:biounlock_mobile/services/session_store.dart';
import 'package:biounlock_mobile/state/app_state.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  test('configureServer validates reachability and persists the url', () async {
    final store = InMemorySessionStore();
    final state = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok({
          'name': 'BioUnlock',
          'version': '0.1.0',
          'rp_id': 'example.com',
          'server_signing_key_fingerprint': 'abc',
          'environment': 'production',
        }),
      }),
    );

    final succeeded = await state.configureServer('example.com');

    expect(succeeded, isTrue);
    expect(state.isConfigured, isTrue);
    expect(state.serverInfo?.rpId, 'example.com');
    expect(await store.readServerUrl(), 'https://example.com');
  });

  test('configureServer rejects an invalid url', () async {
    final state = AppState(
      store: InMemorySessionStore(),
      passkeyService: FakePasskeyService(),
    );
    final succeeded = await state.configureServer('   ');
    expect(succeeded, isFalse);
    expect(state.error, isNotNull);
  });

  test('register stores the session and sets the api token', () async {
    final store = InMemorySessionStore(serverUrl: 'https://example.com');
    final state = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok({
          'name': 'BioUnlock',
          'version': '0.1.0',
          'rp_id': 'example.com',
          'server_signing_key_fingerprint': 'abc',
          'environment': 'production',
        }),
        'POST /api/v1/auth/register': (_) => ok(sessionJson(), 201),
      }),
    );
    await state.init();
    final succeeded = await state.register('user@example.com', 'password123');
    expect(succeeded, isTrue);
    expect(state.isAuthenticated, isTrue);
    expect(state.api!.token, 'session-token');
    expect((await store.readSession())?.token, 'session-token');
  });

  test('init restores a stored session', () async {
    final store = InMemorySessionStore(serverUrl: 'https://example.com');
    final client = routedClient({
      'POST /api/v1/auth/register': (_) => ok(sessionJson(), 201),
      'GET /api/v1/auth/me': (_) => ok(accountJson()),
      'GET /api/v1/server/info': (_) => ok({
        'name': 'BioUnlock',
        'version': '0.1.0',
        'rp_id': 'example.com',
        'server_signing_key_fingerprint': 'abc',
        'environment': 'production',
      }),
    });
    final state = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: client,
    );
    await state.init();
    await state.register('user@example.com', 'password123');

    final restored = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: client,
    );
    await restored.init();
    expect(restored.isAuthenticated, isTrue);
    expect(restored.serverInfo?.name, 'BioUnlock');
  });

  test('resetServer clears configuration', () async {
    final store = InMemorySessionStore(serverUrl: 'https://example.com');
    final state = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok({
          'name': 'BioUnlock',
          'version': '0.1.0',
          'rp_id': 'example.com',
          'server_signing_key_fingerprint': 'abc',
          'environment': 'production',
        }),
      }),
    );
    await state.init();
    await state.resetServer();
    expect(state.isConfigured, isFalse);
    expect(state.isAuthenticated, isFalse);
  });
}
