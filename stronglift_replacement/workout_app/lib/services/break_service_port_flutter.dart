/// The one file in the break feature that touches a platform channel.
library;

import 'dart:developer';
import 'dart:ui';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:vibration/vibration.dart';
import 'package:workout_app/services/break_notification_text.dart';
import 'package:workout_app/services/break_service_port.dart';

/// Channel the break-end alert is posted on.
///
/// VERSIONED ON PURPOSE. Android freezes a channel's importance, sound and
/// vibration the first time it is created, and neither reinstalling nor
/// `adb install -r` resets that. If this channel ever lands with the wrong
/// settings on a device it can only be fixed by creating a NEW one — bump the
/// suffix, never edit `_v1` and hope. The symptom of getting this wrong is a
/// silent alert that looks exactly like a code bug.
const kBreakEndChannelId = 'break_end_v1';

/// Notification id of the break-end alert.
const kBreakEndNotificationId = 8801;

/// Notification id of the terminal "workout complete" message.
const kWorkoutDoneNotificationId = 8802;

/// The real [BreakServicePort], running inside the foreground-service isolate.
class FlutterBreakServicePort implements BreakServicePort {
  /// Creates a port. Cheap: nothing happens until [ensureIsolateReady].
  FlutterBreakServicePort();

  final _notifications = FlutterLocalNotificationsPlugin();
  AudioPlayer? _player;

  // Every method below is a platform-channel passthrough from a BACKGROUND
  // isolate. `flutter test` has no such isolate and no such channels, so none
  // of this can run on the test host; the decisions that lead here all live in
  // break_task_handler.dart, which is covered against a fake port.
  // coverage:ignore-start

  @override
  Future<void> ensureIsolateReady() async {
    // A background isolate starts with no plugin registrations. Without this
    // the sound, the haptic and the notification all fail with
    // MissingPluginException -- silently, because they are fire-and-forget.
    DartPluginRegistrant.ensureInitialized();
    _player ??= AudioPlayer();

    const settings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    );
    await _notifications.initialize(settings: settings);

    await _notifications
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.createNotificationChannel(
          const AndroidNotificationChannel(
            kBreakEndChannelId,
            'Break finished',
            description: 'Sounds when a rest period between sets is over.',
            importance: Importance.max,
            sound: RawResourceAndroidNotificationSound('break_end'),
          ),
        );
  }

  @override
  Future<void> updateNotification(BreakNotificationCopy copy) =>
      FlutterForegroundTask.updateService(
        notificationTitle: copy.title,
        notificationText: copy.body,
      );

  @override
  Future<void> fireBreakEndAlert() async {
    // Two routes on purpose. The mp3 goes out on the MEDIA stream, so it is
    // heard even with the phone on vibrate; the notification goes out on its
    // own max-importance channel, so it still fires if this isolate is busy.
    try {
      await _player?.play(AssetSource('sounds/break_end.mp3'));
    } on Exception catch (error) {
      log(
        'BreakService: the break-end sound failed to play ($error). The '
        'notification alert below is the only cue the user will get.',
        level: 1000,
      );
    }
    if (await Vibration.hasVibrator()) {
      await Vibration.vibrate(duration: 800);
    }
    await _notifications.show(
      id: kBreakEndNotificationId,
      title: 'Break over',
      body: 'Back to the bar.',
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          kBreakEndChannelId,
          'Break finished',
          importance: Importance.max,
          priority: Priority.max,
          category: AndroidNotificationCategory.alarm,
          fullScreenIntent: true,
        ),
      ),
    );
  }

  @override
  void nudgeMainToDrain() =>
      FlutterForegroundTask.sendDataToMain(const {'kind': 'drain'});

  @override
  Future<void> finishAndStop() async {
    await _notifications.show(
      id: kWorkoutDoneNotificationId,
      title: 'Workout complete',
      body: 'Open the app to save it.',
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          kBreakEndChannelId,
          'Break finished',
          importance: Importance.high,
          priority: Priority.high,
        ),
      ),
    );
    await FlutterForegroundTask.stopService();
  }

  // coverage:ignore-end
}
