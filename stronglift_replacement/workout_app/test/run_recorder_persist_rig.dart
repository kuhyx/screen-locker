/// Shared rig of the run recorder persistence tests.
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_checkpoint.dart';
import 'package:workout_app/services/run_recorder.dart';
import 'run_test_fixtures.dart';

final DateTime persistT0 = DateTime.utc(2026, 11, 9, 12);

/// A recorder plus everything it reports, on a clock the test moves.
class PersistHost {
  PersistHost({
    ManualPositionSource? source,
    DateTime? at,
    Duration autoEnd = const Duration(hours: 5),
  }) : source = source ?? ManualPositionSource(),
       now = at ?? persistT0 {
    recorder = RunRecorder(
      sourceFor: () => this.source,
      onKilometre: km.add,
      onSuggestFinish: suggestions.add,
      onAutoEnd: () => autoEnds++,
      onCheckpoint: checkpoints.add,
      clock: () => now,
      autoEndAfter: autoEnd,
    );
  }

  final ManualPositionSource source;
  late final RunRecorder recorder;
  DateTime now;
  final km = <int>[];
  final suggestions = <RunSuggestion>[];
  final checkpoints = <RunCheckpoint>[];
  int autoEnds = 0;

  /// Finishes inside `testWidgets`, where awaiting a stream cancel hangs the
  /// fake-async zone: it runs in the real one instead.
  Future<RunTrack?> finishAfter(WidgetTester tester) async =>
      await tester.runAsync<RunTrack?>(recorder.finish);

  /// Delivers [fixes]; inside `testWidgets` pass the tester, whose pump
  /// drains the queue where a real-time `pumpEventQueue` would hang.
  Future<void> feed(Iterable<GpsFix> fixes, {WidgetTester? tester}) async {
    for (final fix in fixes) {
      source.controller.add(fix);
    }
    await (tester?.pump() ?? pumpEventQueue());
  }
}

RunCheckpoint viaJson(RunCheckpoint c) => RunCheckpoint.fromJson(
  jsonDecode(jsonEncode(c.toJson())) as Map<String, Object?>,
);

Future<RunCheckpoint> checkpointAfter(int fixes, {bool pause = false}) async {
  final h = PersistHost();
  await h.recorder.start();
  await h.feed(straightRun(fixes));
  if (pause) h.recorder.pause();
  final c = h.recorder.checkpoint()!;
  await h.recorder.finish();
  h.recorder.dispose();
  return viaJson(c);
}

class ThrowingSource extends ManualPositionSource {
  @override
  Stream<GpsFix> fixes({Duration interval = const Duration(seconds: 2)}) =>
      throw StateError('provider gone');
}
