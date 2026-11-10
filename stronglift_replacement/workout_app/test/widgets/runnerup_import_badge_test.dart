import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/runnerup_importer.dart';
import 'package:workout_app/widgets/runnerup_import_badge.dart';

void main() {
  Future<void> pump(
    WidgetTester tester,
    ValueNotifier<RunnerUpImportStatus>? status,
  ) => tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: RunnerUpImportBadge(status: status)),
    ),
  );

  testWidgets('shows a spinner while importing, a glyph on failure, and '
      'never any text', (tester) async {
    final status = ValueNotifier(RunnerUpImportStatus.idle);
    await pump(tester, status);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.byIcon(Icons.sync_problem), findsNothing);

    status.value = RunnerUpImportStatus.running;
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    status.value = RunnerUpImportStatus.failed;
    await tester.pump();
    expect(find.byIcon(Icons.sync_problem), findsOneWidget);
    expect(find.byType(Text), findsNothing);

    status.value = RunnerUpImportStatus.done;
    await tester.pump();
    expect(find.byIcon(Icons.sync_problem), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('listens to the live importer status by default', (tester) async {
    runnerUpImportStatus.value = RunnerUpImportStatus.failed;
    await pump(tester, null);
    expect(find.byIcon(Icons.sync_problem), findsOneWidget);
    runnerUpImportStatus.value = RunnerUpImportStatus.idle;
  });
}
