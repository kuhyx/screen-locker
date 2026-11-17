import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/position_source.dart';
import 'package:workout_app/services/run_phase.dart';
import 'package:workout_app/services/run_view.dart';
import 'package:workout_app/services/run_wire.dart';

import '../fake_run_engine.dart';

Map<String, Object?> snapshot(
  FakeRunEngine engine, {
  int from = 0,
  String? suggestion,
  bool prompt = false,
  bool done = false,
  ({bool stored, String reason})? saved,
}) => encodeSnapshot(
  engine,
  from: from,
  suggestion: suggestion,
  prompt: prompt,
  done: done,
  saved: saved,
);

void main() {
  test('a snapshot fills every field', () {
    final engine = FakeRunEngine()
      ..paceTarget = 330
      ..setPhase(RunPhase.recording)
      ..addFix()
      ..addFix();
    final view = RunView()
      ..apply(
        snapshot(
          engine,
          suggestion: 'gpsLost',
          prompt: true,
          done: true,
          saved: (stored: true, reason: 'ok'),
        ),
      );

    expect(view.phase, RunPhase.recording);
    expect(view.seconds, 4);
    expect(view.distanceM, 12);
    expect(view.paceTarget, 330);
    expect(view.pace, isNull);
    expect(view.band, isNull);
    expect(view.suggestion, 'gpsLost');
    expect(view.promptFinish, isTrue);
    expect(view.done, isTrue);
    expect(view.saved, (stored: true, reason: 'ok'));
    expect(view.synced, isTrue);
    expect(view.livePoints.value, hasLength(2));
    view.dispose();
  });

  test('a band name decodes', () {
    final view = RunView();
    final message = snapshot(FakeRunEngine())..['band'] = PaceBand.onPace.name;
    view.apply(message);
    expect(view.band, PaceBand.onPace);
    view.dispose();
  });

  group('points', () {
    test('an increment appends', () {
      final engine = FakeRunEngine()
        ..setPhase(RunPhase.recording)
        ..addFix();
      final view = RunView()..apply(snapshot(engine));
      engine.addFix();
      view.apply(snapshot(engine, from: 1));

      expect(view.livePoints.value, hasLength(2));
      view.dispose();
    });

    test('a gap asks for everything again', () {
      final engine = FakeRunEngine()..setPhase(RunPhase.recording);
      var asked = 0;
      final view = RunView()
        ..onNeedSync = () {
          asked++;
        }
        ..apply(snapshot(engine));
      engine
        ..addFix()
        ..addFix()
        ..addFix();
      view.apply(snapshot(engine, from: 2));

      expect(asked, 1);
      expect(view.livePoints.value, isEmpty);

      view.apply(snapshot(engine));
      expect(view.livePoints.value, hasLength(3));
      expect(asked, 1);
      view.dispose();
    });

    test('a count that does not add up asks again', () {
      final engine = FakeRunEngine()
        ..setPhase(RunPhase.recording)
        ..addFix();
      var asked = 0;
      final view = RunView()..onNeedSync = () {
          asked++;
        };
      final message = snapshot(engine)..['total'] = 5;
      view.apply(message);
      expect(asked, 1);
      view.dispose();
    });

    test('a new run replaces the old points', () {
      final engine = FakeRunEngine()
        ..setPhase(RunPhase.recording)
        ..addFix()
        ..addFix();
      final view = RunView()..apply(snapshot(engine));
      final fresh = FakeRunEngine()..setPhase(RunPhase.recording);
      view.apply(snapshot(fresh));
      expect(view.livePoints.value, isEmpty);
      view.dispose();
    });
  });

  group('access', () {
    test('a refusal becomes the issue while idle', () {
      final view = RunView()..noteAccess(LocationAccess.deniedForever);
      expect(view.issue, RunIssue.deniedForever);
      view.noteAccess(LocationAccess.granted);
      expect(view.issue, RunIssue.none);
      view.noteAccess(LocationAccess.granted);
      expect(view.issue, RunIssue.none);
      view.dispose();
    });

    test('an idle host answer does not wipe the UI refusal', () {
      final view = RunView()..noteAccess(LocationAccess.denied);
      view.apply(snapshot(FakeRunEngine()));
      expect(view.issue, RunIssue.denied);
      view.dispose();
    });

    test('a run is never touched by an access check', () {
      final engine = FakeRunEngine()..setPhase(RunPhase.recording);
      final view = RunView()
        ..apply(snapshot(engine))
        ..noteAccess(LocationAccess.denied);
      expect(view.issue, RunIssue.none);
      view.dispose();
    });

    test('a host issue while idle shows', () {
      final engine = FakeRunEngine()
        ..setPhase(RunPhase.idle, issue: RunIssue.denied);
      final view = RunView()..apply(snapshot(engine));
      expect(view.issue, RunIssue.denied);
      view.dispose();
    });
  });

  test('wire points round-trip with and without altitude', () {
    final engine = FakeRunEngine()..addFix();
    final point = engine.points.single;
    expect(decodePoint(encodePoint(point)), point);
    final withAltitude = decodePoint([
      0,
      1.5,
      2.5,
      3,
      40.0,
    ]);
    expect(withAltitude.altitudeM, 40);
    expect(isRunMessage({'cmd': 'x'}), isFalse);
    expect(isRunMessage('x'), isFalse);
  });
}
