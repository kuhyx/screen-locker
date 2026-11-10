// The last pace target survives a restart (shared_preferences).
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';
import 'package:workout_app/services/pace_target_store.dart';

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  test('nothing stored yet reads as the default 6:00', () async {
    expect(await PrefsPaceTargetStore().load(), kDefaultPaceTarget);
    expect(kDefaultPaceTarget, 360);
  });

  test('saves and reloads the last target', () async {
    await PrefsPaceTargetStore().save(295);
    expect(await PrefsPaceTargetStore().load(), 295);
  });

  test('an out-of-range stored value is clamped on load', () async {
    await SharedPreferencesAsync().setInt(kPaceTargetKey, 5);
    expect(await PrefsPaceTargetStore().load(), 180);
  });

  test('the default store is usable without an injected instance', () async {
    final store = PrefsPaceTargetStore(SharedPreferencesAsync());
    await store.save(400);
    expect(await store.load(), 400);
  });
}
