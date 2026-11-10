import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/position_source_geolocator.dart';
import 'package:workout_app/services/position_source_scripted.dart';

/// A platform that answers from fields instead of a method channel.
class _FakeGeolocator extends GeolocatorPlatform {
  bool serviceOn = true;
  LocationPermission current = LocationPermission.denied;
  LocationPermission afterRequest = LocationPermission.whileInUse;
  int requests = 0;
  LocationSettings? settings;
  List<Position> positions = [];

  @override
  Future<bool> isLocationServiceEnabled() async => serviceOn;

  @override
  Future<LocationPermission> checkPermission() async => current;

  @override
  Future<LocationPermission> requestPermission() async {
    requests++;
    return current = afterRequest;
  }

  @override
  Stream<Position> getPositionStream({LocationSettings? locationSettings}) {
    settings = locationSettings;
    return Stream.fromIterable(positions);
  }
}

Position _position({bool mocked = false}) => Position(
  latitude: 48.8584,
  longitude: 2.2945,
  timestamp: DateTime.utc(2026, 11, 9, 12),
  accuracy: 4.5,
  altitude: 33,
  altitudeAccuracy: 1,
  heading: 0,
  headingAccuracy: 1,
  speed: 2,
  speedAccuracy: 1,
  isMocked: mocked,
);

void main() {
  test('only granted access can read fixes', () {
    expect(LocationAccess.values.where((a) => a.isGranted), [
      LocationAccess.granted,
    ]);
  });

  group('GeolocatorPositionSource', () {
    late _FakeGeolocator platform;
    final original = GeolocatorPlatform.instance;

    setUp(() {
      platform = _FakeGeolocator();
      GeolocatorPlatform.instance = platform;
    });
    tearDown(() => GeolocatorPlatform.instance = original);

    test('service off wins over any permission', () async {
      platform.serviceOn = false;
      expect(
        await GeolocatorPositionSource().requestAccess(),
        LocationAccess.serviceOff,
      );
      expect(platform.requests, 0);
    });

    test('a denied permission is requested once and then granted', () async {
      expect(
        await GeolocatorPositionSource().requestAccess(),
        LocationAccess.granted,
      );
      expect(platform.requests, 1);
    });

    test('an already granted permission is not requested again', () async {
      platform.current = LocationPermission.always;
      expect(
        await GeolocatorPositionSource().requestAccess(),
        LocationAccess.granted,
      );
      expect(platform.requests, 0);
    });

    test('refusals map to denied / deniedForever', () async {
      platform.afterRequest = LocationPermission.denied;
      expect(
        await GeolocatorPositionSource().requestAccess(),
        LocationAccess.denied,
      );
      platform.current = LocationPermission.deniedForever;
      expect(
        await GeolocatorPositionSource().requestAccess(),
        LocationAccess.deniedForever,
      );
      platform.current = LocationPermission.unableToDetermine;
      expect(
        await GeolocatorPositionSource().requestAccess(),
        LocationAccess.denied,
      );
    });

    test('checkAccess reads the state and never prompts', () async {
      final source = GeolocatorPositionSource();
      expect(await source.checkAccess(), LocationAccess.denied);
      platform.current = LocationPermission.whileInUse;
      expect(await source.checkAccess(), LocationAccess.granted);
      platform.current = LocationPermission.deniedForever;
      expect(await source.checkAccess(), LocationAccess.deniedForever);
      platform.serviceOn = false;
      expect(await source.checkAccess(), LocationAccess.serviceOff);
      expect(platform.requests, 0);
    });

    test('fixes maps positions and asks for navigation accuracy', () async {
      platform.positions = [_position(), _position(mocked: true)];
      final fixes = await GeolocatorPositionSource(
        forceLocationManager: true,
      ).fixes(interval: const Duration(seconds: 3)).toList();
      expect(fixes, hasLength(2));
      expect(fixes.first.latitude, 48.8584);
      expect(fixes.first.altitudeM, 33);
      expect(fixes.first.accuracyM, 4.5);
      expect(fixes.first.time, DateTime.utc(2026, 11, 9, 12));
      expect(fixes.first.isMocked, isFalse);
      expect(fixes.last.isMocked, isTrue);
      final android = platform.settings! as AndroidSettings;
      expect(android.accuracy, LocationAccuracy.bestForNavigation);
      expect(android.intervalDuration, const Duration(seconds: 3));
      expect(android.forceLocationManager, isTrue);
    });
  });

  group('ScriptedPositionSource', () {
    final script = [
      GpsFix(
        time: DateTime.utc(2026, 11, 9, 12),
        latitude: 1,
        longitude: 2,
        accuracyM: 3,
      ),
      GpsFix(
        time: DateTime.utc(2026, 11, 9, 12, 0, 2),
        latitude: 1.0001,
        longitude: 2,
        accuracyM: 3,
      ),
    ];

    test('replays the script in order and answers the given access', () async {
      final source = ScriptedPositionSource(
        script,
        access: LocationAccess.deniedForever,
      );
      expect(await source.requestAccess(), LocationAccess.deniedForever);
      expect(await source.checkAccess(), LocationAccess.deniedForever);
      expect(await source.fixes().toList(), script);
    });

    test('defaults to granted and honours a per-fix delay', () async {
      final source = ScriptedPositionSource(
        script,
        fixDelay: const Duration(milliseconds: 1),
      );
      expect(await source.requestAccess(), LocationAccess.granted);
      expect(await source.fixes().length, 2);
    });
  });
}
