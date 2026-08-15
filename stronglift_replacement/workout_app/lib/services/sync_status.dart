/// The four states the home screen's sync card can show, and the pure
/// function that decides between them.
///
/// This exists because a workout was once logged into a void: the app was not
/// connected to Firebase, said nothing about it, and the session did not
/// count. Silence was the bug. The card is the fix, and keeping the decision
/// in a pure function means it can be tested without pumping a widget.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/services/workout_sync_service.dart';

/// How long a successful sync stays "fresh" before the card nags.
///
/// The app is opened before each workout, so anything older than a few hours
/// means the last open did not manage to sync.
const Duration kSyncStaleAfter = Duration(hours: 6);

/// Which of the four card states applies. Order matters -- see
/// [computeSyncStatus].
enum SyncState {
  /// No credentials at all: this device has never been set up.
  notConnected,

  /// Credentials exist but the last attempt errored.
  failed,

  /// Last successful sync is older than [kSyncStaleAfter] (or never happened).
  outOfDate,

  /// Synced within the freshness window.
  synced,
}

/// A resolved sync state plus the detail the card needs to render.
@immutable
class SyncStatus {
  /// Creates a status.
  const SyncStatus({required this.state, this.reason, this.age});

  /// Which card to show.
  final SyncState state;

  /// For [SyncState.failed], the human-readable reason from [PushResult].
  final String? reason;

  /// For [SyncState.outOfDate] and [SyncState.synced], how long ago the last
  /// successful sync was. Null when there has never been one.
  final Duration? age;

  @override
  bool operator ==(Object other) =>
      other is SyncStatus &&
      other.state == state &&
      other.reason == reason &&
      other.age == age;

  @override
  int get hashCode => Object.hash(state, reason, age);

  @override
  String toString() => 'SyncStatus($state, reason: $reason, age: $age)';
}

/// Decides which card to show, first match wins.
///
/// The ordering is the point. On a fresh install there are no credentials
/// *and* no timestamp, and "Not connected" is the useful thing to say --
/// "Out of date" would send the user looking for a sync that never existed.
///
/// - [configured]: does this device have any sync credentials?
/// - [lastResult]: the outcome of the most recent attempt this session.
/// - [lastSyncedAt]: when a sync last succeeded, ever (persisted).
/// - [now]: injected so "3h ago" is testable.
SyncStatus computeSyncStatus({
  required bool configured,
  required DateTime now,
  PushResult? lastResult,
  DateTime? lastSyncedAt,
}) {
  if (!configured) {
    return const SyncStatus(state: SyncState.notConnected);
  }
  if (lastResult != null && !lastResult.pushed) {
    return SyncStatus(state: SyncState.failed, reason: lastResult.reason);
  }
  if (lastSyncedAt == null) {
    return const SyncStatus(state: SyncState.outOfDate);
  }
  final age = now.difference(lastSyncedAt);
  if (age >= kSyncStaleAfter) {
    return SyncStatus(state: SyncState.outOfDate, age: age);
  }
  return SyncStatus(state: SyncState.synced, age: age);
}
