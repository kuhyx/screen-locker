/// The phases and problems of a GPS recording.
library;

/// Where a recording stands.
enum RunPhase {
  /// Nothing recorded yet; the sport can still be chosen.
  idle,

  /// Fixes are being kept and credited.
  recording,

  /// Fixes are ignored; nothing is credited until [RunRecorder.resume].
  paused,

  /// Over; [RunRecorder.finish] has returned the track.
  finished;

  /// True from start to finish: recording or paused.
  bool get isActive => this == recording || this == paused;
}

/// What is wrong with the recording right now (shown as an icon, logged).
enum RunIssue {
  /// Nothing.
  none,

  /// Location permission refused; asking again may work.
  denied,

  /// Location permission refused for good; only system settings can fix it.
  deniedForever,

  /// The device's location switch is off.
  serviceOff,

  /// The newest fix came from a mock-location provider and was dropped.
  mockedLocation,

  /// The location stream reported an error.
  streamError,

  /// Finished with too few usable fixes to make a track; nothing was saved.
  tooShort,
}
