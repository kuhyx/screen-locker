/// Where the last pace target is kept between runs (shared_preferences).
library;

import 'package:shared_preferences/shared_preferences.dart';
import 'package:workout_app/services/pace_band.dart';

/// The preferences key of the last pace target, in seconds per kilometre.
const String kPaceTargetKey = 'run_pace_target_v1';

/// The target the picker starts at when none was ever chosen, 6:00.
const int kDefaultPaceTarget = 360;

/// Reads and writes the last target; an interface so screen tests need no
/// platform channel.
abstract class PaceTargetStore {
  /// The stored target, or [kDefaultPaceTarget].
  Future<int> load();

  /// Stores [seconds] as the last target.
  Future<void> save(int seconds);
}

/// The real store, over `SharedPreferencesAsync` (resolved on first use, so
/// merely owning one costs nothing on the test host).
class PrefsPaceTargetStore implements PaceTargetStore {
  /// Creates a store over [prefs], defaulting to a fresh async instance.
  PrefsPaceTargetStore([SharedPreferencesAsync? prefs]) : _prefs = prefs;

  SharedPreferencesAsync? _prefs;

  SharedPreferencesAsync get _resolved => _prefs ??= SharedPreferencesAsync();

  @override
  Future<int> load() async {
    final stored = await _resolved.getInt(kPaceTargetKey);
    return clampPaceTarget(stored ?? kDefaultPaceTarget);
  }

  @override
  Future<void> save(int seconds) => _resolved.setInt(kPaceTargetKey, seconds);

  /// The target as stored, or null when none was ever chosen (the "off"
  /// state the /sdcard backup carries).
  Future<int?> stored() => _resolved.getInt(kPaceTargetKey);

  /// Puts a backed-up target back; null means none chosen, so a leftover
  /// value is removed rather than kept.
  Future<void> restore(int? seconds) => seconds == null
      ? _resolved.remove(kPaceTargetKey)
      : save(clampPaceTarget(seconds));
}
