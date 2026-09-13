/// Everything the break task handler is allowed to do to the outside world.
library;

import 'package:workout_app/services/break_notification_text.dart';

/// Notification action button ids, as Android hands them back.
abstract final class BreakNotificationAction {
  /// Record the next set at its full target reps.
  static const done = 'done';

  /// Knock one rep off the set that was recorded last.
  static const minusRep = 'minus_rep';

  /// End the running rest early.
  static const skipBreak = 'skip_break';

  /// Every id, in the order the buttons appear on the notification.
  ///
  /// Android allows at most three, which is why `Done` records the full target
  /// reps and `− 1 rep` walks down from there instead of there being a button
  /// per rep count: targets range from 5 to 30 across the plan.
  static List<String> get inButtonOrder => const [done, minusRep, skipBreak];
}

/// The side effects available inside the foreground-service isolate.
///
/// An interface so the task handler's decisions — when to redraw, when to
/// alert, when to stop — can be tested on a machine with no Android on it. The
/// real implementation is the only code in this feature that touches a
/// platform channel.
///
/// Deliberately has no storage method beyond the intent queue's own: the
/// service isolate must never write to sqflite. The CRDT sync layer sits on top
/// of that database and stamps records with a clock the UI isolate owns; a
/// second writer would order its writes outside that sequence.
abstract class BreakServicePort {
  /// Registers plugins in this isolate. Must run before anything else.
  ///
  /// A background isolate starts with no plugin registrations at all, so
  /// without this every later call fails with `MissingPluginException` — and
  /// the break-end sound fails exactly as silently as the bug being fixed.
  Future<void> ensureIsolateReady();

  /// Redraws the ongoing notification.
  Future<void> updateNotification(BreakNotificationCopy copy);

  /// Fires the break-end alert: the sound, the haptic, and the heads-up.
  Future<void> fireBreakEndAlert();

  /// Nudges the UI isolate to drain the intent queue.
  ///
  /// Carries no payload on purpose. The queue is the only path a press takes,
  /// so a nudge that is lost costs nothing and a nudge that arrives twice
  /// cannot apply anything twice.
  void nudgeMainToDrain();

  /// Shows the terminal "workout complete" notification and stops the service.
  Future<void> finishAndStop();
}
