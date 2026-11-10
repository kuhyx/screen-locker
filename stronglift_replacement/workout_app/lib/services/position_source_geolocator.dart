/// The real [PositionSource], backed by the geolocator plugin.
library;

import 'package:geolocator/geolocator.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';

/// Reads fixes through [GeolocatorPlatform.instance], so a test can swap the
/// platform and drive this class without a device.
class GeolocatorPositionSource implements PositionSource {
  /// Creates the source; [forceLocationManager] skips Google Play services.
  GeolocatorPositionSource({this.forceLocationManager = false});

  /// Android: use the legacy LocationManager instead of the fused provider.
  final bool forceLocationManager;

  GeolocatorPlatform get _platform => GeolocatorPlatform.instance;

  @override
  Future<LocationAccess> requestAccess() async {
    if (!await _platform.isLocationServiceEnabled()) {
      return LocationAccess.serviceOff;
    }
    var permission = await _platform.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await _platform.requestPermission();
    }
    return switch (permission) {
      LocationPermission.always ||
      LocationPermission.whileInUse => LocationAccess.granted,
      LocationPermission.deniedForever => LocationAccess.deniedForever,
      LocationPermission.denied ||
      LocationPermission.unableToDetermine => LocationAccess.denied,
    };
  }

  @override
  Stream<GpsFix> fixes({Duration interval = const Duration(seconds: 2)}) =>
      _platform
          .getPositionStream(
            locationSettings: AndroidSettings(
              accuracy: LocationAccuracy.bestForNavigation,
              intervalDuration: interval,
              forceLocationManager: forceLocationManager,
            ),
          )
          .map(
            (p) => GpsFix(
              time: p.timestamp,
              latitude: p.latitude,
              longitude: p.longitude,
              altitudeM: p.altitude,
              accuracyM: p.accuracy,
              isMocked: p.isMocked,
            ),
          );
}
