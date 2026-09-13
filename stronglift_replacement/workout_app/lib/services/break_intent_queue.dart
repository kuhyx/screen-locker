/// The durable hand-off between the foreground service and the workout screen.
library;

import 'dart:async';
import 'dart:developer';

import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/services/break_intent_store.dart';

/// A write-ahead log of notification button presses.
///
/// The foreground service runs in its own isolate that outlives the UI, so a
/// button press cannot simply call into the workout screen — the screen may not
/// exist. Every press is therefore appended here first and applied later, which
/// also makes the "app is alive" and "app was killed" paths the same code.
///
/// The service's live `sendDataToMain` message carries no payload: it is only a
/// nudge to drain. That is what makes double-application impossible rather than
/// merely unlikely.
class BreakIntentQueue {
  /// Creates a queue over [store].
  BreakIntentQueue(this._store);

  /// Last sequence number handed out. Written only by the service isolate.
  static const seqKey = 'workout.break.seq';

  /// The pending intents. Appended by the service, pruned by the UI.
  static const intentsKey = 'workout.break.intents';

  /// Last sequence number applied. Written only by the UI isolate.
  static const lastAppliedKey = 'workout.break.lastApplied';

  /// Beyond this many pending presses the oldest are dropped, loudly.
  ///
  /// A workout is a few dozen presses; anything approaching this means the UI
  /// has not drained for a very long time and the oldest entries are stale.
  static const maxEntries = 64;

  final BreakIntentStore _store;

  bool _draining = false;
  bool _redrainRequested = false;

  /// Appends a press and returns the intent that was recorded.
  ///
  /// Called from the service isolate. The sequence number is written *before*
  /// the list: a crash between the two leaves a gap in the numbering, which the
  /// `seq > lastApplied` filter tolerates. Writing the list first would let two
  /// presses share a number, and the second would be silently swallowed as a
  /// duplicate — a lost press is worse than a skipped number.
  Future<BreakIntent> enqueue({
    required BreakIntentKind kind,
    required int exIdx,
    required int setIdx,
    required DateTime now,
  }) async {
    final seq = await _store.readInt(seqKey) + 1;
    await _store.writeInt(seqKey, seq);

    final intent = BreakIntent(
      seq: seq,
      kind: kind,
      exIdx: exIdx,
      setIdx: setIdx,
      tsMs: now.millisecondsSinceEpoch,
    );
    final entries = [
      ...await _store.readStringList(intentsKey),
      intent.encode(),
    ];
    if (entries.length > maxEntries) {
      final dropped = entries.length - maxEntries;
      log(
        'BreakIntentQueue: queue overflowed at ${entries.length} entries — '
        'dropped the $dropped oldest notification press(es) unapplied. The '
        'workout screen has not drained the queue for a very long time.',
        level: 900,
      );
      entries.removeRange(0, dropped);
    }
    await _store.writeStringList(intentsKey, entries);
    return intent;
  }

  /// Applies every press the UI has not seen yet, oldest first.
  ///
  /// [apply] is called once per intent, in sequence order. `lastApplied` is
  /// committed after each one rather than at the end, so a crash part-way
  /// through resumes from where it stopped instead of replaying work the user
  /// can already see.
  ///
  /// Re-entrant calls do not nest: a nudge that arrives mid-drain schedules one
  /// more pass instead, so a press is never lost and never applied twice.
  Future<void> drain(Future<void> Function(BreakIntent intent) apply) async {
    if (_draining) {
      _redrainRequested = true;
      return;
    }
    _draining = true;
    try {
      do {
        _redrainRequested = false;
        await _drainOnce(apply);
      } while (_redrainRequested);
    } finally {
      _draining = false;
    }
  }

  Future<void> _drainOnce(Future<void> Function(BreakIntent) apply) async {
    final raw = await _store.readStringList(intentsKey);
    if (raw.isEmpty) return;
    var lastApplied = await _store.readInt(lastAppliedKey);

    final pending = <BreakIntent>[];
    for (final entry in raw) {
      final intent = BreakIntent.tryDecode(entry);
      if (intent == null) {
        log(
          'BreakIntentQueue: dropped an unreadable queue entry — a '
          'notification press was lost. Raw text: $entry',
          level: 900,
        );
        continue;
      }
      if (intent.seq > lastApplied) pending.add(intent);
    }
    pending.sort((a, b) => a.seq.compareTo(b.seq));

    for (final intent in pending) {
      await apply(intent);
      lastApplied = intent.seq;
      await _store.writeInt(lastAppliedKey, lastApplied);
    }

    // Re-READ before pruning. `raw` is a snapshot from before the applies, and
    // the service isolate appends to this list whenever the user presses a
    // button -- including while this drain was running. Writing the filtered
    // snapshot back would erase any press that arrived in between, silently.
    final current = await _store.readStringList(intentsKey);
    final keep = [
      for (final entry in current)
        if ((BreakIntent.tryDecode(entry)?.seq ?? -1) > lastApplied) entry,
    ];
    if (keep.length != current.length) {
      await _store.writeStringList(intentsKey, keep);
    }
  }

  /// Forgets every pending press, e.g. when a workout is finished or reset.
  Future<void> clear() async {
    await _store.writeStringList(intentsKey, const []);
    await _store.writeInt(lastAppliedKey, await _store.readInt(seqKey));
  }
}
