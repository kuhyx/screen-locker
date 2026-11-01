import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/ui/theme.dart';
import 'package:workout_app/widgets/data_transfer_buttons.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: buildAppTheme(),
  home: Scaffold(body: child),
);

Future<void> _tapImport(WidgetTester tester, ImportReport? report) async {
  var reloaded = 0;
  await tester.pumpWidget(
    _wrap(
      DataTransferButtons(
        exporter: () async => true,
        importer: () async => report,
        onImported: () => reloaded++,
      ),
    ),
  );
  await tester.tap(find.bySemanticsLabel('Import data'));
  await tester.pumpAndSettle();
  addTearDown(() => expect(reloaded, report == null ? 0 : 1));
}

void main() {
  testWidgets('a full import shows the check', (tester) async {
    await _tapImport(tester, (rows: 2, manualRecords: 1, manualSkipped: false));

    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber), findsNothing);
  });

  testWidgets('skipped manual workouts show a warning, not the check', (
    tester,
  ) async {
    await _tapImport(tester, (rows: 2, manualRecords: 0, manualSkipped: true));

    expect(find.byIcon(Icons.warning_amber), findsOneWidget);
    expect(find.byIcon(Icons.check_circle), findsNothing);
    expect(find.bySemanticsLabel('Manual workouts skipped'), findsOneWidget);
  });

  testWidgets('a cancelled picker shows no outcome icon', (tester) async {
    await _tapImport(tester, null);

    expect(find.byIcon(Icons.check_circle), findsNothing);
    expect(find.byIcon(Icons.warning_amber), findsNothing);
    expect(find.byIcon(Icons.error_outline), findsNothing);
  });

  testWidgets('a failing export shows the error icon', (tester) async {
    await tester.pumpWidget(
      _wrap(
        DataTransferButtons(
          exporter: () async => throw StateError('disk'),
          importer: () async => null,
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Export data'));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.error_outline), findsOneWidget);
  });

  testWidgets('export is a save icon, not a share icon', (tester) async {
    await tester.pumpWidget(
      _wrap(
        DataTransferButtons(
          exporter: () async => true,
          importer: () async => null,
        ),
      ),
    );

    expect(find.byIcon(Icons.save_alt), findsOneWidget);
    expect(find.byIcon(Icons.ios_share), findsNothing);
    expect(find.bySemanticsLabel('Export data'), findsOneWidget);
  });
}
