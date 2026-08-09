/// This install's persisted sync device id.
library;

import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// SharedPreferences key holding this install's device id.
///
/// The same key the sibling apps (`todo`, `home_inventory`, `diet_guard`,
/// `wake_alarm`) use for the same purpose.
const kSyncDeviceIdKey = 'crdt.nodeId';

/// The id this install pushed under before migrating to a persisted uuid.
///
/// Passed to `syncLog` so the log already sitting at `devices/phone/` is
/// treated as this device's own rather than a peer's. Set to null once that
/// path has been reclaimed.
const legacySyncDeviceId = 'phone';

String? _cached;

/// This install's sync device id, for HLC stamping and the pushed path.
///
/// Synchronous because [Hlc] stamping is; call [initSyncDeviceId] once during
/// startup, before any sync runs. Until then this falls back to
/// [legacySyncDeviceId] so a caller that stamps too early still gets a valid
/// (if pre-migration) id rather than crashing.
String get currentSyncDeviceId => _cached ?? legacySyncDeviceId;

/// Loads (or mints and persists) this install's device id.
///
/// A per-install uuid rather than the fixed `phone` constant: two installs
/// sharing an id overwrite each other's pushed file on every tick, and a
/// reinstall would inherit the previous install's CRDT identity.
///
/// Idempotent -- safe to call more than once.
Future<String> initSyncDeviceId({SharedPreferences? prefs}) async {
  final store = prefs ?? await SharedPreferences.getInstance();
  final existing = store.getString(kSyncDeviceIdKey);
  if (existing != null && existing.isNotEmpty) {
    _cached = existing;
    return existing;
  }
  final minted = const Uuid().v4();
  await store.setString(kSyncDeviceIdKey, minted);
  _cached = minted;
  return minted;
}

/// Resets the cached id. Test-only.
void resetSyncDeviceIdForTest() => _cached = null;
