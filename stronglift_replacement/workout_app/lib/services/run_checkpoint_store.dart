/// Where the run's checkpoint lives between process deaths.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:developer';
import 'dart:io';

import 'package:workout_app/services/run_checkpoint.dart';

/// Keeps the newest [RunCheckpoint] of the run in progress.
abstract interface class RunCheckpointStore {
  /// Replaces the stored checkpoint with [c].
  Future<void> save(RunCheckpoint c);

  /// The stored checkpoint, or null when there is none (or it was corrupt).
  Future<RunCheckpoint?> load();

  /// Forgets the checkpoint: the run ended and was saved.
  Future<void> clear();
}

/// A store in memory, for tests and hosts that keep nothing on disk.
class MemoryRunCheckpointStore implements RunCheckpointStore {
  RunCheckpoint? _held;

  @override
  Future<void> save(RunCheckpoint c) async => _held = c;

  @override
  Future<RunCheckpoint?> load() async => _held;

  @override
  Future<void> clear() async => _held = null;
}

void _logLoud(String message) => log(message, level: 1000);

/// One JSON file, written atomically (temp file, then rename) so a kill
/// mid-write leaves the previous checkpoint whole.
///
/// Saves are coalesced: while one write is in flight, later saves replace
/// each other and only the newest is written next, so the 2 s fix stream
/// can never queue up writes behind a slow disk.
class FileRunCheckpointStore implements RunCheckpointStore {
  /// A store at [file]. [clock] stamps the name of a corrupt file moved
  /// aside; [onLoud] hears every problem (default: a level-1000 log).
  FileRunCheckpointStore(
    this.file, {
    this._clock = DateTime.now,
    void Function(String message) onLoud = _logLoud,
  }) : _loud = onLoud;

  /// The checkpoint file.
  final File file;

  final DateTime Function() _clock;
  final void Function(String message) _loud;
  RunCheckpoint? _newest;
  Future<void>? _draining;

  File get _tmp => File('${file.path}.tmp');

  @override
  Future<void> save(RunCheckpoint c) {
    _newest = c;
    return _draining ??= _drain();
  }

  Future<void> _drain() async {
    try {
      while (_newest != null) {
        final c = _newest!;
        _newest = null;
        await _write(c);
      }
    } finally {
      _draining = null;
    }
  }

  Future<void> _write(RunCheckpoint c) async {
    await file.parent.create(recursive: true);
    await _tmp.writeAsString(jsonEncode(c.toJson()), flush: true);
    await _tmp.rename(file.path);
  }

  @override
  Future<RunCheckpoint?> load() async {
    if (!file.existsSync()) return null;
    try {
      final json = jsonDecode(utf8.decode(await file.readAsBytes()));
      if (json is! Map<String, Object?>) {
        throw FormatException(
          'top level is ${json.runtimeType}, not an object',
        );
      }
      return RunCheckpoint.fromJson(json);
    } on FormatException catch (e) {
      log('RunCheckpointStore: corrupt checkpoint (${e.message})', level: 1000);
      await _moveAside(e);
      return null;
    }
  }

  Future<void> _moveAside(FormatException why) async {
    final aside = '${file.path}.corrupt-${_clock().millisecondsSinceEpoch}';
    await file.rename(aside);
    _loud(
      'RunCheckpointStore: the run checkpoint is corrupt (${why.message}); '
      'moved to $aside and starting without it. The run it held is lost.',
    );
  }

  @override
  Future<void> clear() async {
    for (final f in [file, _tmp]) {
      if (f.existsSync()) await f.delete();
    }
  }
}
