/// The seam between the recorder and the platform's location provider.
///
/// Everything above this interface (recorder, map, sandbox replay) is pure
/// Dart and runs on the Linux test host and the desktop target; only
/// `GeolocatorPositionSource` touches the geolocator plugin.
library;

import 'package:workout_app/services/gps_filter.dart';

/// Whether the app may read the location right now.
enum LocationAccess {
  /// Permission granted and the location service is on.
  granted,

  /// Permission refused this time; asking again may work.
  denied,

  /// Permission refused for good; only the system settings can change it.
  deniedForever,

  /// Permission is fine but the device's location switch is off.
  serviceOff;

  /// Whether fixes can be read right now.
  bool get isGranted => this == LocationAccess.granted;
}

/// A stream of GPS fixes plus the permission handshake that guards it.
abstract class PositionSource {
  /// Asks for location permission (this may show the system prompt); never
  /// throws for a refusal.
  Future<LocationAccess> requestAccess();

  /// Reads the access as it stands, without ever prompting. For re-checks
  /// when the app comes back to the foreground: the permission dialog itself
  /// backgrounds the app, so re-asking there would loop.
  Future<LocationAccess> checkAccess();

  /// Fixes roughly every [interval], best accuracy, until cancelled.
  ///
  /// [interval] must stay well under the PC's 30 s credit gap
  /// (`kMaxCreditGapSeconds`): a quieter stream earns nothing.
  Stream<GpsFix> fixes({Duration interval = const Duration(seconds: 2)});
}
