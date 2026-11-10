// The optional pace target on the run screen: the picker before the start, the
// coloured current pace while recording, the cues, the notification.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_audio_platform.dart';
import '_run_screen_fixtures.dart';

String _text(String id) =>
    (find.byKey(Key(id)).evaluate().single.widget as Text).data!;

Color? _colour(WidgetTester tester, String id) =>
    tester.widget<Text>(key(id)).style?.color;

Future<void> _pickTarget(WidgetTester tester, RunHarness h, int target) async {
  h.paceStore.value = target;
  await h.pump(tester);
  await tapKey(tester, 'run_pace_toggle');
}

void main() {
  setUp(installFakeAudioPlatform);

  group('picker', () {
    testWidgets('off by default: only the pace icon, no numbers', (
      tester,
    ) async {
      final h = RunHarness();
      await h.pump(tester);
      expect(key('run_pace_toggle'), findsOneWidget);
      expect(key('run_pace_value'), findsNothing);
      expect(key('run_pace_minus'), findsNothing);
    });

    testWidgets('on: shows the last target and steps it by 0:05', (
      tester,
    ) async {
      final h = RunHarness();
      h.paceStore.value = 300;
      await h.pump(tester);
      await tapKey(tester, 'run_pace_toggle');
      expect(_text('run_pace_value'), '5:00');

      await tester.tap(key('run_pace_plus'));
      await tester.pump();
      expect(_text('run_pace_value'), '5:05');
      await tester.tap(key('run_pace_minus'));
      await tester.pump();
      await tester.tap(key('run_pace_minus'));
      await tester.pump();
      expect(_text('run_pace_value'), '4:55');
      expect(h.paceStore.value, 295);

      await tapKey(tester, 'run_pace_toggle');
      expect(key('run_pace_value'), findsNothing);
    });
  });

  group('recording with a target', () {
    testWidgets('no target: no second number, no cues', (tester) async {
      final h = RunHarness();
      await h.pump(tester);
      await tapKey(tester, 'run_start');
      await h.run(tester, 40);
      expect(key('run_pace_now'), findsNothing);
      expect(h.cues.paceCues, isEmpty);
    });

    testWidgets('on pace: green number, silence, average stays big', (
      tester,
    ) async {
      final h = RunHarness();
      await _pickTarget(tester, h, 335); // 3 m/s is 5:33
      await tapKey(tester, 'run_start');
      await h.run(tester, 40);
      final colors = Theme.of(
        tester.element(key('run_pace')),
      ).extension<AppStatusColors>()!;
      expect(_text('run_pace_now'), '5:33');
      expect(_colour(tester, 'run_pace_now'), colors.success);
      expect(_text('run_pace'), '5:33'); // the run's average
      expect(h.cues.paceCues, isEmpty);
    });

    testWidgets('too slow: red number and one slow cue per 30 s', (
      tester,
    ) async {
      final h = RunHarness();
      await _pickTarget(tester, h, 300); // wants 5:00, runs 5:33
      await tapKey(tester, 'run_start');
      final scheme = Theme.of(tester.element(key('run_pace'))).colorScheme;
      await h.run(tester, 40); // 78 s
      expect(_colour(tester, 'run_pace_now'), scheme.error);
      expect(h.cues.paceCues, [PaceCue.tooSlow, PaceCue.tooSlow]);
    });

    testWidgets('too fast: red number and the other cue', (tester) async {
      final h = RunHarness();
      await _pickTarget(tester, h, 420); // wants 7:00, runs 5:33
      await tapKey(tester, 'run_start');
      await h.run(tester, 14); // 26 s: one cue, then throttled
      expect(h.cues.paceCues, [PaceCue.tooFast]);
    });

    testWidgets('the notification carries the current pace as numbers', (
      tester,
    ) async {
      final h = RunHarness();
      await _pickTarget(tester, h, 335);
      await tapKey(tester, 'run_start');
      await h.run(tester, 40);
      expect(h.service.drawn.last, endsWith('5:35'));
    });
  });
}
