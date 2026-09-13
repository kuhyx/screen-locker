/// Cross-isolate key/value storage for the notification intent queue.
library;

import 'package:shared_preferences/shared_preferences.dart';

/// The handful of reads and writes the intent queue needs.
///
/// An interface rather than `SharedPreferencesAsync` directly so the queue's
/// ordering rules can be tested without a platform channel, and so the one
/// place that talks to the platform is small enough to read in one go.
abstract class BreakIntentStore {
  /// Reads [key], or zero when it has never been written.
  Future<int> readInt(String key);

  /// Writes [value] to [key].
  Future<void> writeInt(String key, int value);

  /// Reads [key], or an empty list when it has never been written.
  Future<List<String>> readStringList(String key);

  /// Writes [value] to [key].
  Future<void> writeStringList(String key, List<String> value);
}

/// The real store, backed by `SharedPreferencesAsync`.
///
/// `SharedPreferencesAsync`, never `SharedPreferences.getInstance()`. The
/// legacy API hands back a snapshot cached at load time, so the UI isolate
/// would keep reading the queue as it looked when the screen opened and would
/// never see anything the foreground service appended. Every notification
/// button would appear to do nothing at all.
class PrefsBreakIntentStore implements BreakIntentStore {
  /// Creates a store over [prefs], defaulting to a fresh async instance.
  PrefsBreakIntentStore([SharedPreferencesAsync? prefs]) : _prefs = prefs;

  /// Resolved on first use, never in the constructor.
  ///
  /// `SharedPreferencesAsync()` throws unless a platform instance is
  /// registered, and the workout screen builds a store in `initState` on every
  /// platform -- including Linux desktop and the test host, where there is no
  /// foreground service to have queued anything in the first place. Deferring
  /// means merely owning a store costs nothing.
  SharedPreferencesAsync? _prefs;

  SharedPreferencesAsync get _resolved => _prefs ??= SharedPreferencesAsync();

  @override
  Future<int> readInt(String key) async => await _resolved.getInt(key) ?? 0;

  @override
  Future<void> writeInt(String key, int value) => _resolved.setInt(key, value);

  @override
  Future<List<String>> readStringList(String key) async =>
      await _resolved.getStringList(key) ?? const [];

  @override
  Future<void> writeStringList(String key, List<String> value) =>
      _resolved.setStringList(key, value);
}
