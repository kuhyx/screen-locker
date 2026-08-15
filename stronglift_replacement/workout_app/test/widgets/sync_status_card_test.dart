import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/sync_status.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/sync_status_card.dart';

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
    expect(find.text('Not connected to sync'), findsOneWidget);
    // The consequence is the whole point of the card -- a workout logged
    // while disconnected does not count, which is what cost a real session.
    expect(find.textContaining('NOT count'), findsOneWidget);
    await tester.tap(find.text('Set up sync'));
    expect(setUpTapped, 1);
    expect(retried, 0);
  });

  testWidgets('failed shows the concrete reason and retries', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SyncStatus(
          state: SyncState.failed,
          reason: 'sync failed: connection refused',
        ),
      ),
    );
    expect(find.text('Sync failed'), findsOneWidget);
    expect(find.textContaining('connection refused'), findsOneWidget);
    await tester.tap(find.text('Retry'));
    expect(retried, 1);
  });

  testWidgets('failed falls back to generic text when reason is null', (
    tester,
  ) async {
    await tester.pumpWidget(wrap(const SyncStatus(state: SyncState.failed)));
    expect(find.textContaining('did not go through'), findsOneWidget);
  });

  testWidgets('outOfDate reports how long ago and retries', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SyncStatus(
          state: SyncState.outOfDate,
          age: Duration(hours: 9),
        ),
      ),
    );
    expect(find.text('Sync out of date'), findsOneWidget);
    expect(find.textContaining('9h ago'), findsOneWidget);
    await tester.tap(find.text('Retry'));
    expect(retried, 1);
  });

  testWidgets('outOfDate with no age says it has never synced', (tester) async {
    await tester.pumpWidget(
      wrap(const SyncStatus(state: SyncState.outOfDate)),
    );
    expect(find.textContaining('never synced'), findsOneWidget);
  });

  testWidgets('synced is a compact line with no button', (tester) async {
    await tester.pumpWidget(
      wrap(
        const SyncStatus(state: SyncState.synced, age: Duration(minutes: 3)),
      ),
    );
    expect(find.textContaining('Synced 3m ago'), findsOneWidget);
    // Healthy state must not carry an action: a card that is always there
    // with a button becomes wallpaper and stops being read.
    expect(find.byType(TextButton), findsNothing);
    expect(find.byType(Card), findsNothing);
  });

  testWidgets('synced with no age still renders', (tester) async {
    await tester.pumpWidget(wrap(const SyncStatus(state: SyncState.synced)));
    expect(find.text('Synced'), findsOneWidget);
  });

  group('describeAge', () {
    test('renders each magnitude the way a human would say it', () {
      expect(SyncStatusCard.describeAge(const Duration(seconds: 5)), 'just now');
      expect(SyncStatusCard.describeAge(const Duration(minutes: 5)), '5m ago');
      expect(SyncStatusCard.describeAge(const Duration(hours: 5)), '5h ago');
      expect(SyncStatusCard.describeAge(const Duration(days: 5)), '5d ago');
    });
  });
}
