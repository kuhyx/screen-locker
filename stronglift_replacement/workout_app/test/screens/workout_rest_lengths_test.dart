// Rest lengths come from the exercise's own settings: warmup, success and
// fail rests, and the fail rest the notification's `−1 rep` re-cuts to.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/widgets/rep_circle.dart';

import '../fake_audio_platform.dart';
import '../fake_break_service.dart';
import '../fake_secure_storage.dart';
import '_workout_screen_test_fixtures.dart';

// Real plan names, so each has a progression-state row to hold its rests.
const _lunge = Exercise(name: 'Dumbbell Lunge', sets: 3, reps: 5, weight: 10);
const _row = Exercise(name: 'Dumbbell Row', sets: 3, reps: 5, weight: 20);

void main() {
  late FakeForegroundBreakClient client;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
    installFakeAudioPlatform();
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    client = FakeForegroundBreakClient();
  });

  Future<void> pumpWithLungeRests(WidgetTester tester) async {
    await tester.runAsync(() async {
      final s = (await StorageService.instance.getExerciseState(_lunge.name))!;
      await StorageService.instance.setExerciseSettings(
        s.copyWith(restSuccessSecs: 200, restFailSecs: 250, restWarmupSecs: 90),
      );
    });
    await pumpWorkout(
      tester,
      wrapWorkout(exercises: const [_lunge, _row], breakClient: client),
    );
  }

  testWidgets('the warmup rest is the exercise\'s own', (tester) async {
    await pumpWithLungeRests(tester);
    await tapReal(tester, find.bySemanticsLabel('Dumbbell Lunge warmup'));
    expect(restSecs(tester), inInclusiveRange(85, 90));
  });

  testWidgets('success and fail rests are the exercise\'s own', (tester) async {
    await pumpWithLungeRests(tester);
    final circle = find.byType(RepCircle).first;
    await tapReal(tester, circle); // target hit -> success rest
    expect(restSecs(tester), inInclusiveRange(195, 200));
    // The notification carries the fail rest for a `−1 rep` press.
    expect(client.pushed.last.breakFailSecs, 250);

    await tapReal(tester, circle); // one rep short -> fail rest
    expect(restSecs(tester), inInclusiveRange(245, 250));
  });

  testWidgets('an exercise left at defaults keeps 3:00 and 5:00', (
    tester,
  ) async {
    await pumpWithLungeRests(tester);
    final rowFirstSet = find.byType(RepCircle).at(_lunge.sets);
    await tapReal(tester, rowFirstSet);
    expect(restSecs(tester), inInclusiveRange(175, 180));
    expect(client.pushed.last.breakFailSecs, 300);
  });
}
