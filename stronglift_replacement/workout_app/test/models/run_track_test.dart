import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';

void main() {
  group('RunSport', () {
    test('maps the TCX sport name both ways', () {
      expect(RunSport.fromTcxName('Running'), RunSport.running);
      expect(RunSport.fromTcxName('Walking'), RunSport.walking);
      expect(RunSport.fromTcxName('Other'), isNull);
      expect(RunSport.fromTcxName(null), isNull);
      expect(RunSport.walking.tcxName, 'Walking');
    });
  });

  group('storage keys', () {
    test('RunSource round-trips and rejects unknown keys', () {
      for (final s in RunSource.values) {
        expect(RunSource.fromStorageKey(s.storageKey), s);
      }
      expect(RunSource.runnerupImport.storageKey, 'runnerup_import');
      expect(() => RunSource.fromStorageKey('nope'), throwsStateError);
    });

    test('RunUploadState round-trips and rejects unknown keys', () {
      for (final s in RunUploadState.values) {
        expect(RunUploadState.fromStorageKey(s.storageKey), s);
      }
      expect(() => RunUploadState.fromStorageKey('nope'), throwsStateError);
    });
  });

  group('RunTrack', () {
    test('idFor is the UTC second-precision Z stamp', () {
      expect(
        RunTrack.idFor(DateTime.utc(2026, 11, 9, 16, 30, 5, 999)),
        '2026-11-09T16:30:05Z',
      );
      expect(
        RunTrack.idFor(DateTime.parse('2026-11-09T17:30:05+01:00')),
        '2026-11-09T16:30:05Z',
      );
    });

    test('started derives the id and normalises times to UTC', () {
      final local = DateTime.parse('2026-11-09T17:30:00+01:00');
      final track = RunTrack.started(
        sport: RunSport.walking,
        startedAt: local,
        points: [
          RunPoint(time: local, latitude: 1, longitude: 2, distanceM: 0),
        ],
        totalSeconds: 0,
        distanceM: 0,
      );
      expect(track.id, '2026-11-09T16:30:00Z');
      expect(track.startedAt.isUtc, isTrue);
      expect(track.points.single.time.isUtc, isTrue);
      expect(track.source, RunSource.app);
    });
  });

  group('RunPoint', () {
    final t = DateTime.utc(2026, 11, 9);
    RunPoint make({double? alt = 1}) => RunPoint(
      time: t,
      latitude: 1,
      longitude: 2,
      altitudeM: alt,
      distanceM: 3,
    );

    test('has value equality', () {
      expect(make(), make());
      expect(make().hashCode, make().hashCode);
      expect(make(), isNot(make(alt: null)));
      expect(make(), isNot('x'));
    });
  });
}
