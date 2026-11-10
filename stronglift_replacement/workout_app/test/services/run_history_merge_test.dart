import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_history_merge.dart';

RunRecord _run(
  DateTime startedAt, {
  RunSport sport = RunSport.running,
  RunSource source = RunSource.app,
}) => RunRecord(
  track: RunTrack.started(
    sport: sport,
    startedAt: startedAt,
    points: const [],
    totalSeconds: 1800,
    distanceM: 5000,
    source: source,
  ),
  uploadState: RunUploadState.never,
  tcxFilename: 'x.tcx',
  tcxSha256: 'x',
);

Map<String, dynamic> _pc(
  String date, {
  String kind = kRunnerUpVerifiedKind,
  String? activity,
}) => {
  'kind': kind,
  'date': date,
  'distance_km': 5.0,
  if (activity != null) 'activity': activity,
};

void main() {
  // Local noon: the same calendar day in every time zone the suite may run in.
  final noon = DateTime(2026, 11, 9, 12);

  test('a local run hides the PC run entry of its day', () {
    final out = withoutLocalRuns([_pc('2026-11-09')], [_run(noon)]);
    expect(out, isEmpty);
  });

  test('another day, or no local run, keeps the PC entry', () {
    final entries = [_pc('2026-11-08'), _pc('2026-11-09')];
    expect(withoutLocalRuns(entries, [_run(noon)]), [_pc('2026-11-08')]);
    expect(withoutLocalRuns(entries, const []), entries);
  });

  test('an imported run covers the day too', () {
    final out = withoutLocalRuns([
      _pc('2026-11-09'),
    ], [_run(noon, source: RunSource.runnerupImport)]);
    expect(out, isEmpty);
  });

  test('sport must match: a walk does not hide a run, nor a run a walk', () {
    final walk = _run(noon, sport: RunSport.walking);
    final pcRun = _pc('2026-11-09');
    final pcWalk = _pc('2026-11-09', activity: 'walking');
    expect(withoutLocalRuns([pcRun], [walk]), [pcRun]);
    expect(withoutLocalRuns([pcWalk], [walk]), isEmpty);
    expect(withoutLocalRuns([pcWalk], [_run(noon)]), [pcWalk]);
  });

  test('other kinds are never hidden', () {
    final manual = _pc('2026-11-09', kind: 'manual_workout');
    expect(withoutLocalRuns([manual], [_run(noon)]), [manual]);
  });

  test('a full timestamp date still matches on its day', () {
    final out = withoutLocalRuns([_pc('2026-11-09T06:30:00')], [_run(noon)]);
    expect(out, isEmpty);
  });

  test('the day is the local one, not the UTC one', () {
    // 00:30 local on the 9th is the 8th in UTC for any zone east of UTC.
    final early = DateTime(2026, 11, 9, 0, 30);
    expect(withoutLocalRuns([_pc('2026-11-09')], [_run(early)]), isEmpty);
  });
}
