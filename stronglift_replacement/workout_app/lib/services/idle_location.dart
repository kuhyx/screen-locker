/// Where the user is before a run starts: display-only fixes for the map.
///
/// These fixes never touch the recorder, the filter or the track -- they only
/// move the idle map's camera and position marker. The watch ends when the run
/// starts (one location stream at a time), and the recorder's own accepted
/// points take over from there.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:latlong2/latlong.dart';
import 'package:workout_app/services/gps_filter.dart';
import 'package:workout_app/services/position_source.dart';

/// Watches the position while idle and reports the access it found.
class IdleLocation {
  /// Creates a watcher over [_source]; [onAccess] hears every access check.
  IdleLocation(this._source, {required this.onAccess});

  final PositionSource _source;

  /// Told the access after each [open] and [recheck].
  final void Function(LocationAccess access) onAccess;

  /// The latest fix, or null before the first one (or once access is lost).
  final position = ValueNotifier<LatLng?>(null);

  /// The last access found, or null before the first check resolves.
  LocationAccess? access;

  StreamSubscription<GpsFix>? _sub;
  bool _closed = false;

  /// Asks for access (this may show the system prompt) and, once granted,
  /// starts watching.
  Future<void> open() async {
    _closed = false;
    await _apply(await _source.requestAccess());
  }

  /// Re-reads the access without prompting (the app came back to the
  /// foreground); a grant starts the watch, a revocation ends it.
  Future<void> recheck() async {
    if (_closed) return;
    await _apply(await _source.checkAccess());
  }

  /// Lets [recheck] work again after [stop], without watching yet: for a start
  /// that was refused, so coming back from settings can recover the screen.
  void reopen() => _closed = false;

  /// Ends the watch (a run took over, or the screen is going away).
  Future<void> stop() async {
    _closed = true;
    await _unwatch();
  }

  Future<void> _apply(LocationAccess found) async {
    if (_closed) return;
    access = found;
    onAccess(found);
    if (found.isGranted) {
      if (_sub != null) return;
      _sub = _source.fixes().listen(_onFix, onError: _onError);
      return;
    }
    position.value = null;
    await _unwatch();
  }

  Future<void> _unwatch() async {
    final cancelling = _sub?.cancel();
    _sub = null;
    await cancelling;
  }

  void _onFix(GpsFix fix) {
    position.value = LatLng(fix.latitude, fix.longitude);
  }

  void _onError(Object error, StackTrace stack) {
    log(
      'IdleLocation: the location stream failed ($error) -- the idle map '
      'keeps the last known position until fixes resume.',
      level: 1000,
      error: error,
      stackTrace: stack,
    );
  }

  /// Stops watching and releases the position notifier.
  Future<void> dispose() async {
    await stop();
    position.dispose();
  }
}
