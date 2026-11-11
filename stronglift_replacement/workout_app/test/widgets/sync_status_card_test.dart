import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/sync_status.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/sync_status_card.dart';

import '../icon_finders.dart';

void main() {
  var retried = 0;
  var setUpTapped = 0;

  setUp(() {
    retried = 0;
    setUpTapped = 0;
  });

  Widget wrap(SyncStatus status) => MaterialApp(
    theme: buildAppTheme(),
    home: Scaffold(
      body: SyncStatusCard(
        status: status,
        onRetry: () => retried++,
        onSetUp: () => setUpTapped++,
      ),
    ),
  );

  testWidgets('notConnected says the workout will not count and offers setup', (
    tester,
  ) async {
    await tester.pumpWidget(
      wrap(const SyncStatus(state: SyncState.notConnected)),
    );
    // The consequence is the whole point of the card -- a workout logged
    // while disconnected does not count, which is what cost a real session.
    expect(iconLabeled(_notConnected), findsOneWidget);
    expect(find.byIcon(Icons.cloud_off), findsOneWidget);
    await tester.tap(iconLabeled('Set up sync'));
    expect(setUpTapped, 1);
    expect(retried, 0);
  });

  testWidgets('failed speaks the concrete reason and retries', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SyncStatus(
          state: SyncState.failed,
          reason: 'sync failed: connection refused',
        ),
      ),
    );
    expect(
      iconLabeled('Sync failed. sync failed: connection refused'),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.sync_problem), findsOneWidget);
    await tester.tap(iconLabeled('Retry'));
    expect(retried, 1);
  });

  testWidgets('failed falls back to a generic reason when it is null', (
    tester,
  ) async {
    await tester.pumpWidget(wrap(const SyncStatus(state: SyncState.failed)));
    expect(
      iconLabeled('Sync failed. The last attempt failed.'),
      findsOneWidget,
    );
  });

  testWidgets('outOfDate shows how long ago and retries', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SyncStatus(state: SyncState.outOfDate, age: Duration(hours: 9)),
      ),
    );
    expect(find.byIcon(Icons.cloud_queue), findsOneWidget);
    expect(find.text('9h'), findsOneWidget);
    expect(
      iconLabeled('Sync out of date. Last synced 9h ago.'),
      findsOneWidget,
    );
    await tester.tap(iconLabeled('Retry'));
    expect(retried, 1);
  });

  testWidgets('outOfDate with no age says it never synced', (tester) async {
    await tester.pumpWidget(wrap(const SyncStatus(state: SyncState.outOfDate)));
    expect(
      iconLabeled('Sync out of date. Never synced successfully.'),
      findsOneWidget,
    );
  });

  testWidgets('synced is a compact line with no button', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SyncStatus(state: SyncState.synced, age: Duration(minutes: 3)),
      ),
    );
    expect(iconLabeled('Synced'), findsOneWidget);
    expect(find.text('3m'), findsOneWidget);
    // Healthy state must not carry an action: a card that is always there
    // with a button becomes wallpaper and stops being read.
    expect(find.byType(IconButton), findsNothing);
    expect(find.byType(Card), findsNothing);
  });

  testWidgets('synced with no age shows only the glyph', (tester) async {
    await tester.pumpWidget(wrap(const SyncStatus(state: SyncState.synced)));
    expect(iconLabeled('Synced'), findsOneWidget);
    expect(find.byType(Text), findsNothing);
  });

  group('describeAge', () {
    test('renders each magnitude as a number and a one-letter unit', () {
      expect(SyncStatusCard.describeAge(const Duration(seconds: 5)), '0m');
      expect(SyncStatusCard.describeAge(const Duration(minutes: 5)), '5m');
      expect(SyncStatusCard.describeAge(const Duration(hours: 5)), '5h');
      expect(SyncStatusCard.describeAge(const Duration(days: 5)), '5d');
    });
  });
}

const _notConnected =
    'Not connected to sync. This workout will NOT count until sync is set up.';
