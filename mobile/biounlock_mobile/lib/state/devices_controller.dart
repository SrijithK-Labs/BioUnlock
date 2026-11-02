import 'package:flutter/foundation.dart';

import '../models/device.dart';
import '../services/api_client.dart';
import '../services/api_exception.dart';

/// Loads, pairs, and revokes the user's PCs.
class DevicesController extends ChangeNotifier {
  DevicesController({required ApiClient api, ApiClient Function()? apiProvider})
    : _api = api,
      _apiProvider = apiProvider;

  final ApiClient _api;
  final ApiClient Function()? _apiProvider;

  List<Device> _devices = const [];
  bool _busy = false;
  String? _error;

  List<Device> get devices => _devices;
  bool get busy => _busy;
  String? get error => _error;

  ApiClient get _client => _apiProvider?.call() ?? _api;

  Future<void> load() async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      _devices = await _client.listDevices();
    } on ApiException catch (error) {
      _error = error.message;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  /// Pairs a PC using the code scanned from its QR and refreshes the list.
  Future<Device?> confirmPairing(String pairingCode) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      final device = await _client.confirmPairing(pairingCode);
      await load();
      return device;
    } on ApiException catch (error) {
      _error = error.message;
      return null;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<bool> revoke(String deviceId) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      await _client.revokeDevice(deviceId);
      await load();
      return true;
    } on ApiException catch (error) {
      _error = error.message;
      return false;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  /// Permanently removes a revoked PC and refreshes the list.
  Future<bool> remove(String deviceId) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      await _client.deleteDevice(deviceId);
      await load();
      return true;
    } on ApiException catch (error) {
      _error = error.message;
      return false;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }
}
