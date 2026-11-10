/// A geolocator platform that answers from fields, for tests that build the
/// real run controller (and so the real position source) without a device.
library;

import 'package:geolocator/geolocator.dart';

/// Location on, permission granted, no positions.
class FakeGeolocator extends GeolocatorPlatform {
  /// Whether the device's location switch is on.
  bool serviceOn = true;

  /// The permission [checkPermission] reports.
  LocationPermission permission = LocationPermission.whileInUse;

  @override
  Future<bool> isLocationServiceEnabled() async => serviceOn;

  @override
  Future<LocationPermission> checkPermission() async => permission;

  @override
  Future<LocationPermission> requestPermission() async => permission;

  @override
  Stream<Position> getPositionStream({LocationSettings? locationSettings}) =>
      const Stream.empty();
}
