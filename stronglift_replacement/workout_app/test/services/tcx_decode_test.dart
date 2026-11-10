@TestOn('vm')
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/tcx_codec.dart';

const String _fixtures = '../../screen_locker/tests/fixtures/run_tcx';

String _tcx({
  String sport = 'Running',
  String id = '<Id>2026-11-09T16:30:00Z</Id>',
  String lapStart = ' StartTime="2026-11-09T16:30:00Z"',
  String points = '',
  String author = '',
}) =>
    '''
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="$sport">
      $id
      <Lap$lapStart>
        <TotalTimeSeconds>60</TotalTimeSeconds>
        <DistanceMeters>100</DistanceMeters>
        <Track>$points</Track>
      </Lap>
    </Activity>
  </Activities>$author
</TrainingCenterDatabase>''';

String _tp(String time, {bool position = true}) =>
    '<Trackpoint><Time>$time</Time>'
    '${position ? '<Position><LatitudeDegrees>1.5</LatitudeDegrees>'
              '<LongitudeDegrees>2.5</LongitudeDegrees></Position>' : ''}'
    '<DistanceMeters>7</DistanceMeters></Trackpoint>';

void main() {
  group('decodeTcx on a real RunnerUp export', () {
    final text = File(
      '$_fixtures/RunnerUp_2026-08-12-17-42-11_Running.tcx',
    ).readAsStringSync();

    test('sums the laps and reads every trackpoint', () {
      final t = decodeTcx(
        text,
        fileName: 'RunnerUp_2026-08-12-17-42-11_Running.tcx',
      );
      expect(t.sport, RunSport.running);
      expect(t.source, RunSource.runnerupImport);
      expect(t.id, '2026-08-12T15:42:11Z');
      expect(t.startedAt, DateTime.utc(2026, 8, 12, 15, 42, 11));
      expect(t.totalSeconds, 624 + 626);
      expect(t.distanceM, closeTo(983.6306 + 980.7304, 1e-3));
      expect(t.points, hasLength(10));
      expect(t.points.first.latitude, closeTo(48.858438, 1e-6));
      expect(t.points.first.altitudeM, closeTo(110.066, 1e-3));
      expect(t.points.first.distanceM, closeTo(2.14297, 1e-4));
    });

    test('works without a file name when the Sport attribute says so', () {
      expect(decodeTcx(text).sport, RunSport.running);
    });
  });

  group('decodeTcx edge cases', () {
    test('_Walking file name wins over Sport="Other" (RunnerUp walks)', () {
      final t = decodeTcx(
        _tcx(sport: 'Other'),
        fileName: 'RunnerUp_Pixel_6a_2026-11-09-17-30-00_Walking.tcx',
      );
      expect(t.sport, RunSport.walking);
    });

    test('Sport="Walking" without a file name is a walk', () {
      expect(decodeTcx(_tcx(sport: 'Walking')).sport, RunSport.walking);
    });

    test('an unsupported sport is a FormatException', () {
      expect(
        () => decodeTcx(_tcx(sport: 'Biking')),
        throwsA(isA<FormatException>()),
      );
      expect(
        () => decodeTcx(_tcx(sport: 'Other'), fileName: 'x_Biking.tcx'),
        throwsA(isA<FormatException>()),
      );
    });

    test('malformed XML and a missing Activity are FormatExceptions', () {
      expect(() => decodeTcx('<a'), throwsA(isA<FormatException>()));
      expect(
        () => decodeTcx('<TrainingCenterDatabase/>'),
        throwsA(isA<FormatException>()),
      );
    });

    test('no Id falls back to the lap start, then to the first point', () {
      final lap = decodeTcx(_tcx(id: ''));
      expect(lap.id, '2026-11-09T16:30:00Z');
      final pts = decodeTcx(
        _tcx(id: '', lapStart: '', points: _tp('2026-11-09T10:00:00Z')),
      );
      expect(pts.startedAt, DateTime.utc(2026, 11, 9, 10));
      expect(
        () => decodeTcx(_tcx(id: '', lapStart: '')),
        throwsA(isA<FormatException>()),
      );
    });

    test(
      'points without a position or a usable time are skipped, rest sorted',
      () {
        final t = decodeTcx(
          _tcx(
            points:
                _tp('2026-11-09T16:30:20Z') +
                _tp('2026-11-09T16:30:10Z', position: false) +
                _tp('garbage') +
                _tp('2026-11-09T16:30:05Z'),
          ),
        );
        expect(t.points.map((p) => p.time.second), [5, 20]);
      },
    );

    test('a lap with unreadable totals counts as zero', () {
      final t = decodeTcx(
        _tcx().replaceAll('>60<', '>x<').replaceAll('>100<', '>y<'),
      );
      expect(t.totalSeconds, 0);
      expect(t.distanceM, 0);
    });

    test('a foreign Author is an import, ours is an app file', () {
      expect(
        decodeTcx(
          _tcx(author: '<Author><Name>org.runnerup - 2.11</Name></Author>'),
        ).source,
        RunSource.runnerupImport,
      );
      expect(
        decodeTcx(
          _tcx(author: '<Author><Name>$kRunSourceName</Name></Author>'),
        ).source,
        RunSource.app,
      );
    });
  });
}
