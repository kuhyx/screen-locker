/// The workout's foreground-service brain, minus every platform call.
library;

import 'dart:async';
import 'dart:developer';

import 'package:workout_app/models/break_intent.dart';
import 'package:workout_app/models/break_snapshot.dart';
import 'package:workout_app/services/break_clock.dart';
import 'package:workout_app/services/break_intent_queue.dart';
import 'package:workout_app/services/break_notification_text.dart';
import 'package:workout_app/services/break_service_port.dart';

/// Drives the ongoing notification and the break-end alert.
///
/// Lives in its own isolate with no access to the workout screen, so it works
/// from a snapshot the UI pushes and records what the user presses into a
/// durable queue for the UI to apply whenever it next exists.
class BreakTaskHandler {
  /// Creates a handler over [port] and [queue].
  BreakTaskHandler(this._port, this._queue);

  final BreakServicePort _port;
  final BreakIntentQueue _queue;

  BreakSnapshot? _snapshot;
  BreakNotificationCopy? _lastDrawn;
  int _alertedEndMs = 0;

  /// The snapshot currently driving the notification; for tests.
  BreakSnapshot? get snapshot => _snapshot;

  /// Prepares the isolate. Call from `TaskHandler.onStart`.
  ///
  /// [now] is passed in rather than read here so the handler has no hidden
  /// clock: every time-dependent decision it makes is reproducible.
  Future<void> start(Object? initialData, DateTime now) async {
    await _port.ensureIsolateReady();
    _applyData(initialData);
    await _redraw(now);
  }

  /// Handles a fresh snapshot pushed by the UI isolate.
  Future<void> receiveData(Object? data, DateTime now) async {
    _applyData(data);
    await _redraw(now);
  }

  /// The once-a-second tick: redraw if the text moved, alert if the rest ended.
  Future<void> tick(DateTime now) async {
    final snapshot = _snapshot;
    if (snapshot == null) return;

    if (snapshot.hasBreak && snapshot.breakEndMs != _alertedEndMs) {
      final clock = BreakClock(
        endTime: DateTime.fromMillisecondsSinceEpoch(snapshot.breakEndMs),
        durationSecs: snapshot.breakDurationSecs,
      );
      if (clock.expiredAt(now)) {
        // Stamped before the alert, not after: if the alert throws, the user
        // gets one failed attempt rather than the same sound every second.
        _alertedEndMs = snapshot.breakEndMs;
        await _port.fireBreakEndAlert();
      }
    }
    await _redraw(now);
  }

  /// Records a notification button press and nudges the UI to apply it.
  Future<void> pressButton(String id, DateTime now) async {
    final snapshot = _snapshot;
    if (snapshot == null) {
      log(
        'BreakTaskHandler: ignored notification button "$id" — the service has '
        'no workout snapshot yet, so there is no set it could refer to.',
        level: 900,
      );
      return;
    }
    final resolved = _resolve(id, snapshot);
    if (resolved == null) return;

    await _queue.enqueue(
      kind: resolved.kind,
      exIdx: resolved.exIdx,
      setIdx: resolved.setIdx,
      now: now,
    );
    _snapshot = _predict(resolved.kind, snapshot, now);
    _port.nudgeMainToDrain();

    if (_snapshot!.setsRemaining <= 0) {
      // Nothing left to record, and the UI may never come back to stop us --
      // the user can finish a whole workout from the notification. Stopping
      // here is what keeps the service from outliving the workout.
      await _port.finishAndStop();
      return;
    }
    await _redraw(now);
  }

  void _applyData(Object? data) {
    if (data is! Map) {
      log(
        'BreakTaskHandler: ignored task data of unexpected type '
        '${data.runtimeType} — the notification still shows the previous '
        'workout state.',
        level: 900,
      );
      return;
    }
    final snapshot = BreakSnapshot.tryFromMap(data.cast<Object?, Object?>());
    if (snapshot == null) {
      log(
        'BreakTaskHandler: ignored a malformed workout snapshot — the '
        'notification still shows the previous state. Payload: $data',
        level: 900,
      );
      return;
    }
    _snapshot = snapshot;
  }

  _ResolvedPress? _resolve(String id, BreakSnapshot s) {
    switch (id) {
      case BreakNotificationAction.done:
        if (!s.hasNextSet) {
          log(
            'BreakTaskHandler: ignored "Done" — every set is already '
            'recorded. Open the app to finish the workout.',
            level: 900,
          );
          return null;
        }
        return _ResolvedPress(BreakIntentKind.done, s.nextExIdx, s.nextSetIdx);
      case BreakNotificationAction.minusRep:
        if (s.lastExIdx < 0 || s.lastSetIdx < 0) {
          log(
            'BreakTaskHandler: ignored "− 1 rep" — no set has been recorded '
            'yet, so there is nothing to take a rep off.',
            level: 900,
          );
          return null;
        }
        return _ResolvedPress(
          BreakIntentKind.minusRep,
          s.lastExIdx,
          s.lastSetIdx,
        );
      case BreakNotificationAction.skipBreak:
        if (!s.hasBreak) {
          log(
            'BreakTaskHandler: ignored "Skip break" — no rest period is '
            'running.',
            level: 900,
          );
          return null;
        }
        return _ResolvedPress(
          BreakIntentKind.skipBreak,
          s.breakForExIdx,
          s.breakForSetIdx,
        );
      default:
        log(
          'BreakTaskHandler: ignored unknown notification button id "$id".',
          level: 900,
        );
        return null;
    }
  }

  /// Guesses the new state so the notification reacts to the press at once.
  ///
  /// The UI overwrites this with the truth as soon as it drains the queue —
  /// but it may be dead, and a button that visibly does nothing reads as
  /// broken. Only the fields the press certainly changes are moved.
  BreakSnapshot _predict(
    BreakIntentKind kind,
    BreakSnapshot s,
    DateTime now,
  ) {
    switch (kind) {
      case BreakIntentKind.skipBreak:
        return s.copyWith(breakEndMs: 0);
      case BreakIntentKind.done:
        // A rest starts, but only the screen knows whether this was the
        // exercise's last set. Clear the break and let the UI's snapshot set
        // the real deadline a moment later.
        return s.copyWith(breakEndMs: 0, setsRemaining: s.setsRemaining - 1);
      case BreakIntentKind.minusRep:
        if (!s.hasBreak || s.breakForSetIdx < 0) return s;
        // A decrement turns a success into a failure, which is the longer
        // rest. Re-cut from the start, exactly as the screen does.
        const failSecs = 300;
        final clock = BreakClock(
          endTime: DateTime.fromMillisecondsSinceEpoch(s.breakEndMs),
          durationSecs: s.breakDurationSecs,
        ).withDuration(failSecs);
        return s.copyWith(
          breakEndMs: clock.endTime.millisecondsSinceEpoch,
          breakDurationSecs: failSecs,
          breakLabel: 'Rest (5 min — keep going!)',
        );
    }
  }

  Future<void> _redraw(DateTime now) async {
    final snapshot = _snapshot;
    if (snapshot == null) return;
    final copy = BreakNotificationText.render(snapshot, now);
    // Only when the words changed. An unconditional per-second update makes
    // the notification flicker and costs battery for nothing.
    if (copy == _lastDrawn) return;
    _lastDrawn = copy;
    await _port.updateNotification(copy);
  }
}

class _ResolvedPress {
  const _ResolvedPress(this.kind, this.exIdx, this.setIdx);

  final BreakIntentKind kind;
  final int exIdx;
  final int setIdx;
}
