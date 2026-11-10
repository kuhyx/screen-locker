@TestOn('vm')
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/run_math.dart';
import 'package:workout_app/services/tcx_codec.dart';

import '../run_test_fixtures.dart';

/// A run with a GPS dropout, written by the app's own filter and TCX writer.
///
/// 30 min at 3 m/s, a fix every 20 s, except that the signal is gone between
/// second 600 and 720. The PC credits a dropout that moved at 1 m/s or more
/// (`MIN_DROPOUT_SPEED_MPS`), so the cumulative `DistanceMeters` must jump
/// 360 m across it. The Python twin, `screen_locker/tests/test_run_tcx_golden.py`,
/// feeds the SAME checked-in file to the real verifier. Regenerate it with
/// `UPDATE_GOLDEN=1 flutter test test/services/run_dropout_tcx_test.dart`.
const String _dir = '../../screen_locker/tests/fixtures/run_tcx';
const String _file = 'RunnerUp_2026-11-09-18-00-00_Running.tcx';

RunTrack _recordedRun() {
  final filter = GpsFilter();
  for (var s = 0; s <= 1800; s += 20) {
    if (s > 600 && s < 720) continue; // the dropout
    final fix = fixAt(s, s * 3.0);
    filter.add(
      GpsFix(
        time: DateTime.utc(2026, 11, 9, 17).add(Duration(seconds: s)),
        latitude: fix.latitude,
        longitude: fix.longitude,
        altitudeM: 30,
        accuracyM: 5,
      ),
    );
  }
  final points = filter.points;
  return RunTrack.started(
    sport: RunSport.running,
    startedAt: points.first.time,
    points: points,
    totalSeconds: movingSeconds(points),
    distanceM: filter.distanceM,
  );
}

void main() {
  final track = _recordedRun();

  test('cumulative DistanceMeters jumps across the dropout', () {
    final back = decodeTcx(encodeTcx(track), fileName: _file);
    final before = back.points.firstWhere(
      (p) => p.time.minute == 10 && p.time.second == 0,
    );
    final after = back.points.firstWhere(
      (p) => p.time.minute == 12 && p.time.second == 0,
    );
    expect(before.distanceM, closeTo(1800, 0.5));
    expect(after.distanceM - before.distanceM, closeTo(360, 0.5));
  });

  test('lap distance and moving time count the dropout', () {
    expect(track.distanceM, closeTo(5400, 1));
    expect(track.totalSeconds, 1800);
  });

  test('encodes to exactly the checked-in file the PC test reads', () {
    final encoded = encodeTcx(track);
    final file = File('$_dir/$_file');
    if (Platform.environment['UPDATE_GOLDEN'] == '1') {
      file.writeAsStringSync(encoded);
    }
    expect(file.readAsStringSync(), encoded);
    expect(tcxFilename(track, utcOffset: const Duration(minutes: 60)), _file);
  });
}
