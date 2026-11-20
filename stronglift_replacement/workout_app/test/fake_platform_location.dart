/// A platform_location fake that answers from fields, for tests that build
/// the real run controller (and so the real position source) without a
/// device.
library;

import 'package:platform_location/platform_location.dart';

/// Location on, permission granted, no fixes unless [positions] says so.
class FakePlatformLocation extends PlatformLocation {
  /// Whether the device's location switch is on.
  bool serviceOn = true;

  /// The permission [checkPermission] reports.
  LocationPermissionState current = LocationPermissionState.granted;

  /// What a [requestPermission] call turns [current] into.
  LocationPermissionState? afterRequest;

  /// How many times [requestPermission] ran.
  int requests = 0;

  /// The `precise` flag of the last request.
  bool? lastPrecise;

  /// The interval the last [fixes] call asked for.
  Duration? interval;

  /// What [fixes] emits.
  List<LocationFix> positions = [];

  @override
  Future<bool> isLocationEnabled() async => serviceOn;

  @override
  Future<LocationPermissionState> checkPermission() async => current;

  @override
  Future<LocationPermissionState> requestPermission({
    bool precise = true,
  }) async {
    requests++;
    lastPrecise = precise;
    return current = afterRequest ?? current;
  }

  @override
  Future<LocationFix> currentLocation() async => positions.first;

  @override
  Stream<LocationFix> fixes({Duration interval = const Duration(seconds: 2)}) {
    this.interval = interval;
    return Stream.fromIterable(positions);
  }
}
