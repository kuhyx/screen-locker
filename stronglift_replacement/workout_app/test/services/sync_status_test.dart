import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/sync_status.dart';
import 'package:workout_app/services/workout_sync_service.dart';

final _now = DateTime(2026, 8, 15, 18);

void main() {
  group('computeSyncStatus', () {
    test('no credentials wins even with a fresh timestamp', () {
      // Ordering matters: a device with no credentials must be told to set
      // sync up, not that it is merely stale.
      final status = computeSyncStatus(
        configured: false,
        now: _now,
        lastSyncedAt: _now.subtract(const Duration(minutes: 1)),
      );
      expect(status.state, SyncState.notConnected);
    });

    test('first run — no credentials AND no timestamp — is notConnected', () {
      final status = computeSyncStatus(configured: false, now: _now);
      expect(status.state, SyncState.notConnected);
    });

    test('a failed attempt beats a fresh timestamp', () {
      final status = computeSyncStatus(
        configured: true,
        now: _now,
        lastResult: const PushResult(pushed: false, reason: 'boom'),
        lastSyncedAt: _now.subtract(const Duration(minutes: 1)),
      );
      expect(status.state, SyncState.failed);
      expect(status.reason, 'boom');
    });

    test('configured but never synced is outOfDate with no age', () {
      final status = computeSyncStatus(configured: true, now: _now);
      expect(status.state, SyncState.outOfDate);
      expect(status.age, isNull);
    });

    test('exactly at the staleness boundary is outOfDate', () {
      final status = computeSyncStatus(
        configured: true,
        now: _now,
        lastSyncedAt: _now.subtract(kSyncStaleAfter),
      );
      expect(status.state, SyncState.outOfDate);
      expect(status.age, kSyncStaleAfter);
    });

    test('just inside the staleness boundary is synced', () {
      final status = computeSyncStatus(
        configured: true,
        now: _now,
        lastSyncedAt: _now.subtract(
          kSyncStaleAfter - const Duration(minutes: 1),
        ),
      );
      expect(status.state, SyncState.synced);
    });

    test('a successful result with a fresh timestamp is synced', () {
      final status = computeSyncStatus(
        configured: true,
        now: _now,
        lastResult: const PushResult(pushed: true, reason: 'synced'),
        lastSyncedAt: _now.subtract(const Duration(minutes: 3)),
      );
      expect(status.state, SyncState.synced);
      expect(status.age, const Duration(minutes: 3));
    });
  });

  group('SyncStatus value semantics', () {
    test('equal fields compare equal and hash alike', () {
      const a = SyncStatus(state: SyncState.failed, reason: 'x');
      const b = SyncStatus(state: SyncState.failed, reason: 'x');
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing fields compare unequal', () {
      const a = SyncStatus(state: SyncState.failed, reason: 'x');
      const b = SyncStatus(state: SyncState.failed, reason: 'y');
      const c = SyncStatus(state: SyncState.synced, reason: 'x');
      expect(a, isNot(b));
      expect(a, isNot(c));
      expect(a, isNot(const SyncStatus(state: SyncState.failed, reason: 'x',
          age: Duration(seconds: 1))));
    });

    test('toString names the state and reason', () {
      const status = SyncStatus(state: SyncState.failed, reason: 'boom');
      expect(status.toString(), contains('failed'));
      expect(status.toString(), contains('boom'));
    });
  });
}
