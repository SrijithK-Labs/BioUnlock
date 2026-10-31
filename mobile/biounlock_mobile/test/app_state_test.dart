import 'package:biounlock_mobile/services/api_token_store.dart';
import 'package:biounlock_mobile/services/enrollment_token_store.dart';
import 'package:biounlock_mobile/services/preferences_store.dart';
import 'package:biounlock_mobile/services/server_url_store.dart';
import 'package:biounlock_mobile/state/app_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

void main() {
  test('configureServer validates reachability and persists the url', () async {
    final store = InMemoryServerUrlStore();
    final state = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
      }),
    );

    final succeeded = await state.configureServer('example.com');

    expect(succeeded, isTrue);
    expect(state.isConfigured, isTrue);
    expect(state.serverInfo?.rpId, 'example.com');
    expect(await store.readServerUrl(), 'https://example.com');
  });

  test('configureServer persists the API token and sends it', () async {
    final tokenStore = InMemoryApiTokenStore();
    final headers = <String?>[];
    final state = AppState(
      store: InMemoryServerUrlStore(),
      tokenStore: tokenStore,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (request) {
          headers.add(request.headers['Authorization']);
          return ok(serverInfoJson());
        },
      }),
    );

    final succeeded = await state.configureServer('example.com', token: 'abc123');

    expect(succeeded, isTrue);
    expect(state.apiToken, 'abc123');
    expect(await tokenStore.readToken(), 'abc123');
    expect(headers, ['Bearer abc123']);
  });

  test('init restores a stored API token', () async {
    final headers = <String?>[];
    final state = AppState(
      store: InMemoryServerUrlStore(serverUrl: 'https://example.com'),
      tokenStore: InMemoryApiTokenStore(token: 'stored-token'),
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (request) {
          headers.add(request.headers['Authorization']);
          return ok(serverInfoJson());
        },
      }),
    );

    await state.init();

    expect(state.apiToken, 'stored-token');
    expect(headers, ['Bearer stored-token']);
  });

  test('configureServer sends a stored enrollment token on passkey changes', () async {
    final headers = <String?>[];
    final state = AppState(
      store: InMemoryServerUrlStore(),
      tokenStore: InMemoryApiTokenStore(token: 'api-token'),
      enrollmentTokenStore: InMemoryEnrollmentTokenStore(token: 'enroll-token'),
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
        'POST /api/v1/webauthn/register/begin': (request) {
          headers.add(request.headers['X-BioUnlock-Enrollment']);
          return ok({'challenge_id': 'chal-1', 'options': {}});
        },
      }),
    );

    await state.init();
    await state.configureServer('example.com');
    await state.api!.passkeyRegisterBegin();

    expect(state.enrollmentToken, 'enroll-token');
    expect(headers, ['enroll-token']);
  });

  test('setEnrollmentToken persists the value and rebuilds the client', () async {
    final store = InMemoryEnrollmentTokenStore();
    final headers = <String?>[];
    final state = AppState(
      store: InMemoryServerUrlStore(),
      enrollmentTokenStore: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
        'POST /api/v1/webauthn/register/begin': (request) {
          headers.add(request.headers['X-BioUnlock-Enrollment']);
          return ok({'challenge_id': 'chal-1', 'options': {}});
        },
      }),
    );

    await state.configureServer('example.com');
    await state.setEnrollmentToken('  new-token  ');
    await state.api!.passkeyRegisterBegin();

    expect(state.enrollmentToken, 'new-token');
    expect(await store.readToken(), 'new-token');
    expect(headers, ['new-token']);
  });

  test('resetServer clears the stored enrollment token', () async {
    final store = InMemoryEnrollmentTokenStore(token: 'enroll-token');
    final state = AppState(
      store: InMemoryServerUrlStore(serverUrl: 'https://example.com'),
      enrollmentTokenStore: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
      }),
    );
    await state.init();

    await state.resetServer();

    expect(state.enrollmentToken, isNull);
    expect(await store.readToken(), '');
  });

  test('init does not send stored token to an unsafe saved URL', () async {
    var requests = 0;
    final state = AppState(
      store: InMemoryServerUrlStore(serverUrl: 'http://example.com'),
      tokenStore: InMemoryApiTokenStore(token: 'stored-token'),
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) {
          requests++;
          return ok(serverInfoJson());
        },
      }),
    );

    await state.init();

    expect(requests, 0);
    expect(state.isConfigured, isFalse);
  });

  test('configureServer accepts a plain http LAN url', () async {
    final store = InMemoryServerUrlStore();
    final state = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
      }),
    );

    final succeeded = await state.configureServer('http://192.168.1.10:8000');

    expect(succeeded, isTrue);
    expect(state.serverUrl, 'http://192.168.1.10:8000');
    expect(await store.readServerUrl(), 'http://192.168.1.10:8000');
  });

  test('configureServer rejects cleartext public server urls', () async {
    final state = AppState(
      store: InMemoryServerUrlStore(),
      passkeyService: FakePasskeyService(),
    );

    final succeeded = await state.configureServer('http://example.com');

    expect(succeeded, isFalse);
    expect(state.error, isNotNull);
  });

  test('configureServer rejects an invalid url', () async {
    final state = AppState(
      store: InMemoryServerUrlStore(),
      passkeyService: FakePasskeyService(),
    );
    final succeeded = await state.configureServer('   ');
    expect(succeeded, isFalse);
    expect(state.error, isNotNull);
  });

  test('init restores a stored server url without any authentication', () async {
    final store = InMemoryServerUrlStore(serverUrl: 'https://example.com');
    final state = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
      }),
    );

    await state.init();

    expect(state.isConfigured, isTrue);
    expect(state.serverUrl, 'https://example.com');
    expect(state.serverInfo?.name, 'BioUnlock');
  });

  test('init stays unconfigured when no url is stored', () async {
    final state = AppState(
      store: InMemoryServerUrlStore(),
      passkeyService: FakePasskeyService(),
    );

    await state.init();

    expect(state.initialized, isTrue);
    expect(state.isConfigured, isFalse);
  });

  test('resetServer clears the stored configuration', () async {
    final store = InMemoryServerUrlStore(serverUrl: 'https://example.com');
    final state = AppState(
      store: store,
      passkeyService: FakePasskeyService(),
      httpClient: routedClient({
        'GET /api/v1/server/info': (_) => ok(serverInfoJson()),
      }),
    );
    await state.init();
    await state.resetServer();
    expect(state.isConfigured, isFalse);
    expect(state.serverUrl, isNull);
    expect(await store.readServerUrl(), '');
  });

  test('theme defaults to system and persists changes', () async {
    final preferences = InMemoryPreferencesStore();
    final state = AppState(
      store: InMemoryServerUrlStore(),
      passkeyService: FakePasskeyService(),
      preferences: preferences,
    );

    expect(state.themeMode, ThemeMode.system);

    await state.setThemeMode(ThemeMode.dark);

    expect(state.themeMode, ThemeMode.dark);
    expect(await preferences.readThemeMode(), 'dark');
  });

  test('init restores a stored theme mode', () async {
    final state = AppState(
      store: InMemoryServerUrlStore(),
      passkeyService: FakePasskeyService(),
      preferences: InMemoryPreferencesStore(themeMode: 'light'),
    );

    await state.init();

    expect(state.themeMode, ThemeMode.light);
  });
}