/// The real [PositionSource], backed by the platform_location plugin
/// (AOSP LocationManager; no Google Play services in the APK).
library;

import 'package:platform_location/platform_location.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';

/// Reads fixes through [PlatformLocation.instance], so a test can swap the
/// platform and drive this class without a device.
class LocationManagerPositionSource implements PositionSource {
  PlatformLocation get _platform => PlatformLocation.instance;

  @override
  Future<LocationAccess> requestAccess() async {
    if (!await _platform.isLocationEnabled()) {
      return LocationAccess.serviceOff;
    }
    var permission = await _platform.checkPermission();
    if (permission != LocationPermissionState.granted) {
      // Asked again even after a refusal: only the request itself can tell
      // Android's "don't ask again" (deniedForever) apart from "denied".
      permission = await _platform.requestPermission();
    }
    return _access(permission);
  }

  @override
  Future<LocationAccess> checkAccess() async {
    if (!await _platform.isLocationEnabled()) {
      return LocationAccess.serviceOff;
    }
    return _access(await _platform.checkPermission());
  }

  static LocationAccess _access(LocationPermissionState permission) =>
      switch (permission) {
        LocationPermissionState.granted => LocationAccess.granted,
        LocationPermissionState.deniedForever => LocationAccess.deniedForever,
        LocationPermissionState.denied => LocationAccess.denied,
      };

  @override
  Stream<GpsFix> fixes({Duration interval = const Duration(seconds: 2)}) =>
      _platform
          .fixes(interval: interval)
          .map(
            (p) => GpsFix(
              time: p.time,
              latitude: p.latitude,
              longitude: p.longitude,
              altitudeM: p.altitude,
              accuracyM: p.accuracy,
              isMocked: p.isMock,
            ),
          );
}
