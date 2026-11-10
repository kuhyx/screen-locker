@TestOn('vm')
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_math.dart';
import 'package:workout_app/services/tcx_codec.dart';

/// Cross-language golden test for the TCX the PC credits.
///
/// Each language's own round trip passes happily while the other side's
/// parser disagrees, so this test encodes the tracks in `golden_tracks.json`
/// and compares the result byte for byte with the checked-in `.tcx` files.
/// The Python twin, `screen_locker/tests/test_run_tcx_golden.py`, feeds those
/// SAME files to the real verifier and asserts the km / minutes in the same
/// JSON. Regenerate the files after a deliberate codec change with
/// `UPDATE_GOLDEN=1 flutter test test/services/tcx_golden_fixture_test.dart`.
const String _dir = '../../screen_locker/tests/fixtures/run_tcx';

RunTrack _track(Map<String, dynamic> spec) {
  final points = [
    for (final raw in spec['points'] as List<dynamic>)
      RunPoint(
        time: DateTime.parse((raw as List<dynamic>)[0] as String),
        latitude: (raw[1] as num).toDouble(),
        longitude: (raw[2] as num).toDouble(),
        altitudeM: (raw[3] as num).toDouble(),
        distanceM: (raw[4] as num).toDouble(),
      ),
  ];
  return RunTrack.started(
    sport: RunSport.fromTcxName(spec['sport'] as String)!,
    startedAt: DateTime.parse(spec['started_at'] as String),
    points: points,
    totalSeconds: spec['total_seconds'] as int,
    distanceM: (spec['distance_m'] as num).toDouble(),
  );
}

void main() {
  final tracks =
      jsonDecode(File('$_dir/golden_tracks.json').readAsStringSync())
          as Map<String, dynamic>;
  final update = Platform.environment['UPDATE_GOLDEN'] == '1';

  for (final entry in tracks.entries) {
    final spec = entry.value as Map<String, dynamic>;
    final track = _track(spec);
    final file = File('$_dir/${spec['file']}');

    group('golden ${entry.key}', () {
      test('encodes to exactly the checked-in file', () {
        final encoded = encodeTcx(track);
        if (update) file.writeAsStringSync(encoded);
        expect(file.readAsStringSync(), encoded);
      });

      test('file name is the local-time stamp the PC globs for', () {
        final offset = Duration(minutes: spec['utc_offset_minutes'] as int);
        expect(tcxFilename(track, utcOffset: offset), spec['file']);
      });

      test('stored moving time equals the app-side moving-time rule', () {
        expect(movingSeconds(track.points), track.totalSeconds);
      });

      test('the checked-in file decodes back to the same track', () {
        final back = decodeTcx(
          file.readAsStringSync(),
          fileName: spec['file'] as String,
        );
        expect(back.sport, track.sport);
        expect(back.source, RunSource.app);
        expect(back.totalSeconds, track.totalSeconds);
        expect(back.points, hasLength(track.points.length));
        expect(back.distanceM, closeTo(track.distanceM, 1e-3));
      });
    });
  }
}
