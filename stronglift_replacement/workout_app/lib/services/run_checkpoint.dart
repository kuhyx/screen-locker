/// Everything needed to rebuild a [RunRecorder] after the process died.
///
/// The recorder offers one after every accepted fix and on pause or resume;
/// the host stores it (see `run_checkpoint_store.dart`). The JSON is versioned
/// and strict: [RunCheckpoint.fromJson] throws a [FormatException] on anything
/// it does not understand, so a damaged file is reported, never half-read.
library;

import 'package:flutter/foundation.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/run_phase.dart';

/// The JSON layout version written by [RunCheckpoint.toJson].
const int kCheckpointVersion = 1;

/// A snapshot of an active run: recording or paused.
@immutable
class RunCheckpoint {
  /// Creates a checkpoint; times are normalised to UTC.
  RunCheckpoint({
    required DateTime startedAt,
    required DateTime savedAt,
    required this.phase,
    required this.points,
    required this.movingSeconds,
    required this.distanceM,
    required this.km,
    required this.segmentBreak,
    required this.jumps,
    this.paceTargetSeconds,
  }) : startedAt = startedAt.toUtc(),
       savedAt = savedAt.toUtc();

  /// Reads a checkpoint written by [toJson]; throws [FormatException] when
  /// [json] is of another version, is missing a field or has a wrong type.
  factory RunCheckpoint.fromJson(Map<String, Object?> json) {
    if (json['v'] != kCheckpointVersion) {
      throw FormatException('unsupported checkpoint version ${json['v']}');
    }
    final phase = RunPhase.values.asNameMap()[_field<String>(json, 'phase')];
    if (phase != RunPhase.recording && phase != RunPhase.paused) {
      throw FormatException('checkpoint phase ${json['phase']} is not active');
    }
    return RunCheckpoint(
      startedAt: _time(json, 'startedAt'),
      savedAt: _time(json, 'savedAt'),
      phase: phase!,
      points: [
        for (final p in _field<List<Object?>>(json, 'points')) _point(p),
      ],
      movingSeconds: _field<int>(json, 'moving'),
      distanceM: _field<num>(json, 'distance').toDouble(),
      km: _field<int>(json, 'km'),
      segmentBreak: _field<bool>(json, 'segBreak'),
      jumps: _field<int>(json, 'jumps'),
      paceTargetSeconds: _optional<int>(json, 'target'),
    );
  }

  /// When the run began (wall clock, UTC); the auto-end is measured from it.
  final DateTime startedAt;

  /// When this snapshot was taken (UTC).
  final DateTime savedAt;

  /// Recording or paused.
  final RunPhase phase;

  /// Accepted points so far, with their segment and bridge markers.
  final List<RunPoint> points;

  /// Credited moving time in seconds.
  final int movingSeconds;

  /// Credited distance in metres.
  final double distanceM;

  /// Whole kilometres already announced.
  final int km;

  /// Whether a pause is still waiting for its next fix (starts a segment).
  final bool segmentBreak;

  /// Consecutive too-fast fixes the filter had seen.
  final int jumps;

  /// The pace target in seconds per kilometre, or null when off.
  final int? paceTargetSeconds;

  /// The track id the run will save under (its first point, else its start).
  String get id =>
      RunTrack.idFor(points.isEmpty ? startedAt : points.first.time);

  /// A JSON-encodable form, read back by [RunCheckpoint.fromJson].
  Map<String, Object?> toJson() => {
    'v': kCheckpointVersion,
    'id': id,
    'startedAt': startedAt.toIso8601String(),
    'savedAt': savedAt.toIso8601String(),
    'phase': phase.name,
    'moving': movingSeconds,
    'distance': distanceM,
    'km': km,
    'segBreak': segmentBreak,
    'jumps': jumps,
    'target': paceTargetSeconds,
    // [epoch ms, lat, lon, altitude|null, credited distance, link index]
    'points': [
      for (final p in points)
        [
          p.time.millisecondsSinceEpoch,
          p.latitude,
          p.longitude,
          p.altitudeM,
          p.distanceM,
          p.link.index,
        ],
    ],
  };
}

T _field<T>(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value is T) return value;
  throw FormatException('checkpoint field "$key" is missing or not a $T');
}

T? _optional<T>(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value == null || value is T) return value as T?;
  throw FormatException('checkpoint field "$key" is not a $T');
}

DateTime _time(Map<String, Object?> json, String key) {
  final parsed = DateTime.tryParse(_field<String>(json, key));
  if (parsed == null) throw FormatException('checkpoint "$key" is no time');
  return parsed;
}

RunPoint _point(Object? raw) {
  if (raw is! List<Object?> || raw.length != 6) {
    throw FormatException('checkpoint point $raw is not 6 values');
  }
  final ms = raw[0];
  final lat = raw[1];
  final lon = raw[2];
  final alt = raw[3];
  final dist = raw[4];
  final link = raw[5];
  if (ms is! int ||
      lat is! num ||
      lon is! num ||
      (alt != null && alt is! num) ||
      dist is! num ||
      link is! int ||
      link < 0 ||
      link >= RunLink.values.length) {
    throw FormatException('checkpoint point $raw has a bad value');
  }
  return RunPoint(
    time: DateTime.fromMillisecondsSinceEpoch(ms, isUtc: true),
    latitude: lat.toDouble(),
    longitude: lon.toDouble(),
    altitudeM: (alt as num?)?.toDouble(),
    distanceM: dist.toDouble(),
    link: RunLink.values[link],
  );
}
