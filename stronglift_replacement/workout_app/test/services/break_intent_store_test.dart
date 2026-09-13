// Exercises the REAL PrefsBreakIntentStore, not a fake: the point of this file
// is to prove the SharedPreferencesAsync wiring works, since getting it wrong
// (the legacy cached API) would make every notification button silently dead.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:workout_app/services/break_intent_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late PrefsBreakIntentStore store;

  setUp(() {
    SharedPreferencesAsyncPlatform.instance = InMemorySharedPreferencesAsync
        .empty();
    store = PrefsBreakIntentStore();
  });

  test('an unwritten int reads as zero, not null', () async {
    expect(await store.readInt('workout.break.seq'), 0);
  });

  test('an unwritten list reads as empty, not null', () async {
    expect(await store.readStringList('workout.break.intents'), isEmpty);
  });

  test('ints round-trip', () async {
    await store.writeInt('workout.break.seq', 42);
    expect(await store.readInt('workout.break.seq'), 42);
  });

  test('string lists round-trip', () async {
    await store.writeStringList('workout.break.intents', ['a', 'b']);
    expect(await store.readStringList('workout.break.intents'), ['a', 'b']);
  });

  test('accepts an injected SharedPreferencesAsync', () async {
    final injected = PrefsBreakIntentStore(SharedPreferencesAsync());
    await injected.writeInt('k', 3);
    expect(await injected.readInt('k'), 3);
  });
}
