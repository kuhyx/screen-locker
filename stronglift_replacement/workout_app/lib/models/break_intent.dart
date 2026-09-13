/// A workout action the user triggered from the status-bar notification.
library;

import 'dart:convert';
import 'dart:developer';

/// The three things a notification button can ask the workout screen to do.
enum BreakIntentKind {
  /// Record the target set as completed at its full target reps.
  done,

  /// Knock one rep off an already-recorded set.
  minusRep,

  /// End the running rest period early.
  skipBreak;

  /// Parses [name] back into a kind, or null when it is not one of these.
  static BreakIntentKind? tryParse(String name) {
    for (final kind in BreakIntentKind.values) {
      if (kind.name == name) return kind;
    }
    return null;
  }
}

/// One durable, self-describing button press.
///
/// Self-describing matters: the foreground service resolves which set a press
/// refers to *at press time* and writes those indices down. Re-deriving "the
/// most recent set" when the queue is drained would resolve against state the
/// user never saw, which is how a decrement lands on the wrong set.
class BreakIntent {
  /// Creates an intent.
  const BreakIntent({
    required this.seq,
    required this.kind,
    required this.exIdx,
    required this.setIdx,
    required this.tsMs,
  });

  /// Rebuilds an intent from [json], or returns null if it is not one.
  ///
  /// Total rather than throwing: a malformed entry must never wedge the drain
  /// loop, and the caller logs each rejection with its raw text.
  static BreakIntent? tryDecode(String json) {
    final Object? decoded;
    try {
      decoded = jsonDecode(json);
    } on FormatException catch (error) {
      log(
        'BreakIntent: a queued notification press is unreadable and will be '
        'skipped — the press is lost. $error. Raw text: $json',
        level: 900,
      );
      return null;
    }
    if (decoded is! Map<String, dynamic>) return null;
    final seq = decoded['seq'];
    final kindName = decoded['kind'];
    final exIdx = decoded['exIdx'];
    final setIdx = decoded['setIdx'];
    final tsMs = decoded['tsMs'];
    if (seq is! int || kindName is! String || exIdx is! int) return null;
    if (setIdx is! int || tsMs is! int) return null;
    final kind = BreakIntentKind.tryParse(kindName);
    if (kind == null) return null;
    return BreakIntent(
      seq: seq,
      kind: kind,
      exIdx: exIdx,
      setIdx: setIdx,
      tsMs: tsMs,
    );
  }

  /// Monotonic sequence number, allocated by the service isolate.
  final int seq;

  /// What the user asked for.
  final BreakIntentKind kind;

  /// Exercise this press referred to, or -1 when it referred to no set.
  final int exIdx;

  /// Set this press referred to, or -1 when it referred to no set.
  final int setIdx;

  /// When the button was pressed, epoch milliseconds.
  final int tsMs;

  /// Serializes this intent for the durable queue.
  String encode() => jsonEncode({
    'seq': seq,
    'kind': kind.name,
    'exIdx': exIdx,
    'setIdx': setIdx,
    'tsMs': tsMs,
  });

  @override
  String toString() => 'BreakIntent(#$seq ${kind.name} [$exIdx][$setIdx])';
}
