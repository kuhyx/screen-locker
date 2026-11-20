import 'package:flutter_test/flutter_test.dart';
import 'package:platform_location/platform_location.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/position_source_location_manager.dart';
import 'package:workout_app/services/position_source_scripted.dart';

import '../fake_platform_location.dart';

LocationFix _position({bool mocked = false}) => LocationFix(
  latitude: 48.8584,
  longitude: 2.2945,
  time: DateTime.utc(2026, 11, 9, 12),
  accuracy: 4.5,
  altitude: 33,
  isMock: mocked,
);

void main() {
  test('only granted access can read fixes', () {
    expect(LocationAccess.values.where((a) => a.isGranted), [
      LocationAccess.granted,
    ]);
  });

  group('LocationManagerPositionSource', () {
    late FakePlatformLocation platform;
    final original = PlatformLocation.instance;

    setUp(() {
      platform = FakePlatformLocation()
        ..current = LocationPermissionState.denied
        ..afterRequest = LocationPermissionState.granted;
      PlatformLocation.instance = platform;
    });
    tearDown(() => PlatformLocation.instance = original);

    test('service off wins over any permission', () async {
      platform.serviceOn = false;
      expect(
        await LocationManagerPositionSource().requestAccess(),
        LocationAccess.serviceOff,
      );
      expect(platform.requests, 0);
    });

    test(
      'a denied permission is requested once, precise, then granted',
      () async {
        expect(
          await LocationManagerPositionSource().requestAccess(),
          LocationAccess.granted,
        );
        expect(platform.requests, 1);
        expect(platform.lastPrecise, isTrue);
      },
    );

    test('an already granted permission is not requested again', () async {
      platform.current = LocationPermissionState.granted;
      expect(
        await LocationManagerPositionSource().requestAccess(),
        LocationAccess.granted,
      );
      expect(platform.requests, 0);
    });

    test('refusals map to denied / deniedForever', () async {
      platform.afterRequest = LocationPermissionState.denied;
      expect(
        await LocationManagerPositionSource().requestAccess(),
        LocationAccess.denied,
      );
      platform.afterRequest = LocationPermissionState.deniedForever;
      expect(
        await LocationManagerPositionSource().requestAccess(),
        LocationAccess.deniedForever,
      );
    });

    test('checkAccess reads the state and never prompts', () async {
      final source = LocationManagerPositionSource();
      expect(await source.checkAccess(), LocationAccess.denied);
      platform.current = LocationPermissionState.granted;
      expect(await source.checkAccess(), LocationAccess.granted);
      platform.current = LocationPermissionState.deniedForever;
      expect(await source.checkAccess(), LocationAccess.deniedForever);
      platform.serviceOn = false;
      expect(await source.checkAccess(), LocationAccess.serviceOff);
      expect(platform.requests, 0);
    });

    test('fixes maps platform fixes at the asked interval', () async {
      platform.positions = [_position(), _position(mocked: true)];
      final fixes = await LocationManagerPositionSource()
          .fixes(interval: const Duration(seconds: 3))
          .toList();
      expect(fixes, hasLength(2));
      expect(fixes.first.latitude, 48.8584);
      expect(fixes.first.longitude, 2.2945);
      expect(fixes.first.altitudeM, 33);
      expect(fixes.first.accuracyM, 4.5);
      expect(fixes.first.time, DateTime.utc(2026, 11, 9, 12));
      expect(fixes.first.isMocked, isFalse);
      expect(fixes.last.isMocked, isTrue);
      expect(platform.interval, const Duration(seconds: 3));
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
