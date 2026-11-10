/// A recorded run or walk: the one shape the recorder, the TCX codec, the
/// database and the map all share.
library;

import 'package:flutter/foundation.dart';

/// The sports the app records.
enum RunSport {
  /// A run. The PC credits every GPS activity alike: a day's distance OR
  /// moving time, whatever the sport.
  running('Running', 'Running'),

  /// A walk; read from old files only (the app records everything as a run).
  ///
  /// Written as `Sport="Other"` exactly like RunnerUp does (the TCX schema
  /// only knows Running, Biking and Other); the `_Walking.tcx` file-name
  /// suffix is what marks it a walk.
  walking('Walking', 'Other');

  const RunSport(this.tcxName, this.tcxSport);

  /// The sport's name: the `_<name>.tcx` file-name suffix the PC keys on, and
  /// the `runs.sport` column.
  final String tcxName;

  /// The schema-valid `Sport="..."` attribute the encoder writes.
  final String tcxSport;

  /// The sport named [tcxName] (also accepts the Strava-style
  /// `Sport="Walking"`), or null for anything the app does not record.
  static RunSport? fromTcxName(String? tcxName) {
    for (final sport in values) {
      if (sport.tcxName == tcxName) return sport;
    }
    return null;
  }
}

/// Where a track came from; stored as `runs.source`.
enum RunSource {
  /// Recorded by this app.
  app('app'),

  /// Parsed from a RunnerUp export (history import).
  runnerupImport('runnerup_import');

  const RunSource(this.storageKey);

  /// The value in the `runs.source` column.
  final String storageKey;

  /// The source stored as [key]; throws on an unknown key.
  static RunSource fromStorageKey(String key) =>
      values.firstWhere((s) => s.storageKey == key);
}

/// One accepted GPS fix.
@immutable
class RunPoint {
  /// Creates a point; [time] is normalised to UTC.
  RunPoint({
    required DateTime time,
    required this.latitude,
    required this.longitude,
    required this.distanceM,
    this.altitudeM,
  }) : time = time.toUtc();

  /// When the fix was taken (UTC).
  final DateTime time;

  /// Degrees north.
  final double latitude;

  /// Degrees east.
  final double longitude;

  /// Metres above sea level, when the device reports it.
  final double? altitudeM;

  /// Cumulative credited distance from the start, in metres.
  ///
  /// The PC derives speed from the difference between two points'
  /// values, so this is the field the recorder must keep honest.
  final double distanceM;

  @override
  bool operator ==(Object other) =>
      other is RunPoint &&
      other.time == time &&
      other.latitude == latitude &&
      other.longitude == longitude &&
      other.altitudeM == altitudeM &&
      other.distanceM == distanceM;

  @override
  int get hashCode =>
      Object.hash(time, latitude, longitude, altitudeM, distanceM);
}

/// A finished (or in-progress) track.
@immutable
class RunTrack {
  /// Creates a track; [startedAt] is normalised to UTC.
  RunTrack({
    required this.id,
    required this.sport,
    required DateTime startedAt,
    required this.points,
    required this.totalSeconds,
    required this.distanceM,
    this.source = RunSource.app,
  }) : startedAt = startedAt.toUtc();

  /// A track whose [id] is derived from [startedAt] (see [idFor]).
  factory RunTrack.started({
    required RunSport sport,
    required DateTime startedAt,
    required List<RunPoint> points,
    required int totalSeconds,
    required double distanceM,
    RunSource source = RunSource.app,
  }) => RunTrack(
    id: idFor(startedAt),
    sport: sport,
    startedAt: startedAt,
    points: points,
    totalSeconds: totalSeconds,
    distanceM: distanceM,
    source: source,
  );

  /// The TCX `<Id>`: the start instant, UTC, second precision.
  ///
  /// The PC deduplicates a run's copies (inbox and `processed/`) by this
  /// string, so two different runs must never share one.
  static String idFor(DateTime startedAt) {
    final u = startedAt.toUtc();
    String two(int v) => v.toString().padLeft(2, '0');
    return '${u.year.toString().padLeft(4, '0')}-${two(u.month)}-${two(u.day)}'
        'T${two(u.hour)}:${two(u.minute)}:${two(u.second)}Z';
  }

  /// The TCX `<Id>` and the database key.
  final String id;

  /// Running or walking.
  final RunSport sport;

  /// When recording started (UTC).
  final DateTime startedAt;

  /// Accepted fixes in time order.
  final List<RunPoint> points;

  /// Moving time in seconds (not elapsed): what the PC reads as the duration.
  final int totalSeconds;

  /// Credited distance in metres.
  final double distanceM;

  /// Recorded here or imported.
  final RunSource source;
}
