/// A queue whose state the test sets by hand.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/services/run_uploader.dart';

/// Stands in for [RunUploader] where a widget only reads its state.
class FakeRunUploader extends RunUploader {
  /// Creates a fake queue at [initial].
  FakeRunUploader([
    RunUploadStatus initial = const RunUploadStatus(UploadHealth.idle, 0),
  ]) : state = ValueNotifier(initial);

  /// The state the badge listens to; assign `.value` to change it.
  final ValueNotifier<RunUploadStatus> state;

  /// How many times a pass was requested.
  int passes = 0;

  @override
  ValueListenable<RunUploadStatus> get status => state;

  @override
  Future<RunUploadStatus> uploadPending() async {
    passes++;
    return state.value;
  }
}
