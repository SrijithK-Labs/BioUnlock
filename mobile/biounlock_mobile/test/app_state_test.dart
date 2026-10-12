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