// The feedback cues: a haptic on recording a set, and a haptic, a chime and
// an arriving dialog on finishing. Reward the RECORDING, never the number.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_intent_store.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/rep_circle.dart';
import 'package:workout_app/widgets/workout_summary_dialog.dart';

import '../fake_audio_platform.dart';
import '../fake_break_service.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';

const _select = 'HapticFeedbackType.selectionClick';
const _medium = 'HapticFeedbackType.mediumImpact';

void main() {
  late FakeAudioRecorder audio;
  late List<String> haptics;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    audio = installFakeAudioPlatform();
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    haptics = [];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
          if (call.method == 'HapticFeedback.vibrate') {
            haptics.add(call.arguments as String);
          }
          return null;
        });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null);
  });

  Future<void> finish(WidgetTester tester) async {
    await tester.runAsync(() async {
      await tester.tap(find.widgetWithText(TextButton, 'Finish'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
      await tester.pump();
      await tester.tap(find.widgetWithText(TextButton, 'Finish').last);
      await Future<void>.delayed(const Duration(milliseconds: 800));
      await tester.pump();
    });
    await tester.pump();
  }

  Future<void> setSound(WidgetTester tester, {required bool enabled}) => tester
      .runAsync(() => StorageService.instance.setSoundEnabled(enabled: enabled))
      .then((_) {});

  Map<String, dynamic> partialSaved() => {
    ...completeSaved(),
    'doneReps': [
      [3, 2, 0],
      [5, 4, 1],
    ],
  };

  group('recording a set', () {
    testWidgets('the first tap clicks, once', (tester) async {
      await pumpWorkout(tester, wrapWorkout());
      await tapReal(tester, find.byType(RepCircle).first);
      expect(haptics, [_select]);
    });

    testWidgets('a rep decrement does not click again', (tester) async {
      await pumpWorkout(tester, wrapWorkout());
      await tapReal(tester, find.byType(RepCircle).first);
      await tapReal(tester, find.byType(RepCircle).first);
      expect(haptics, [_select]);
    });

    testWidgets('deleting a set (long press) is silent', (tester) async {
      await pumpWorkout(tester, wrapWorkout());
      await tapReal(tester, find.byType(RepCircle).first);
      haptics.clear();
      await longPressReal(tester, find.byType(RepCircle).first);
      expect(haptics, isEmpty);
    });

    testWidgets('a tap refused during a rest does not click', (tester) async {
      await pumpWorkout(tester, wrapWorkout());
      await tapReal(tester, find.byType(RepCircle).first);
      haptics.clear();
      await tapReal(tester, find.byType(RepCircle).at(1));
      expect(haptics, isEmpty, reason: 'nothing was recorded');
    });

    testWidgets('the warmup circle clicks when it is ticked', (tester) async {
      await pumpWorkout(tester, wrapWorkout());
      await tapReal(tester, find.bySemanticsLabel('Squat warmup'));
      expect(haptics, [_select]);
    });

    testWidgets('a press from the notification does not buzz the pocket', (
      tester,
    ) async {
      final client = FakeForegroundBreakClient();
      final queue = BreakIntentQueue(PrefsBreakIntentStore());
      await tester.runAsync(
        () => queue.enqueue(
          kind: BreakIntentKind.done,
          exIdx: 0,
          setIdx: 0,
          now: DateTime.now(),
        ),
      );
      await pumpWorkout(
        tester,
        wrapWorkout(savedState: blankSaved(), breakClient: client),
      );
      await tester.runAsync(() async {
        client.onNudge!();
        await Future<void>.delayed(const Duration(milliseconds: 400));
      });
      await tester.pump();
      expect(haptics, isEmpty);
    });
  });

  group('finishing a workout', () {
    testWidgets('mediumImpact and the chime, with the summary shown', (
      tester,
    ) async {
      await pumpWorkout(tester, wrapWorkout(savedState: completeSaved()));
      await finish(tester);
      expect(find.byType(WorkoutSummaryDialog), findsOneWidget);
      expect(haptics, contains(_medium));
      expect(
        audio.resumedSources.where((s) => s.contains('workout_done')),
        hasLength(1),
      );
    });

    testWidgets('a failed workout gets exactly the same cue', (tester) async {
      await pumpWorkout(tester, wrapWorkout(savedState: partialSaved()));
      await finish(tester);
      expect(find.textContaining('Workout Done'), findsOneWidget);
      expect(haptics, contains(_medium));
      expect(
        audio.resumedSources.where((s) => s.contains('workout_done')),
        hasLength(1),
      );
    });

    testWidgets('sound off: still the haptic, no chime', (tester) async {
      await setSound(tester, enabled: false);
      await pumpWorkout(tester, wrapWorkout(savedState: completeSaved()));
      await finish(tester);
      expect(haptics, contains(_medium));
      expect(audio.resumedSources, isEmpty);
    });

    testWidgets('a chime that cannot play is logged, not fatal', (
      tester,
    ) async {
      audio.failNextPlay = true;
      final logs = <String>[];
      final original = debugPrint;
      debugPrint = (message, {wrapWidth}) => logs.add(message ?? '');
      try {
        await pumpWorkout(tester, wrapWorkout(savedState: completeSaved()));
        await finish(tester);
      } finally {
        debugPrint = original;
      }
      expect(find.byType(WorkoutSummaryDialog), findsOneWidget);
      expect(logs.where((l) => l.contains('finish chime failed')), isNotEmpty);
    });

    testWidgets('the summary arrives instead of appearing', (tester) async {
      await pumpWorkout(tester, wrapWorkout(savedState: completeSaved()));
      await finish(tester);
      final fade = find.ancestor(
        of: find.byType(WorkoutSummaryDialog),
        matching: find.byType(FadeTransition),
      );
      final early = tester
          .widgetList<FadeTransition>(fade)
          .map((f) => f.opacity.value)
          .reduce((a, b) => a < b ? a : b);
      expect(early, lessThan(1), reason: 'mid-arrival, not yet opaque');
      await tester.pumpAndSettle();
      expect(
        tester
            .widgetList<FadeTransition>(fade)
            .map((f) => f.opacity.value)
            .reduce((a, b) => a < b ? a : b),
        1.0,
      );
    });

    testWidgets('with OS animations removed it is there at once', (
      tester,
    ) async {
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await pumpWorkout(tester, wrapWorkout(savedState: completeSaved()));
      await finish(tester);
      final fade = find.ancestor(
        of: find.byType(WorkoutSummaryDialog),
        matching: find.byType(FadeTransition),
      );
      for (final f in tester.widgetList<FadeTransition>(fade)) {
        expect(f.opacity.value, 1.0);
      }
      expect(haptics, contains(_medium), reason: 'haptics ignore the flag');
      expect(audio.resumedSources, isNotEmpty, reason: 'and so does sound');
    });
  });
}
