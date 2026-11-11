/// textgate guard: collects every word a screen PAINTS.
///
/// Walks the render tree (every [RenderParagraph], so Text, RichText, button
/// labels, AppBar titles, SnackBars and dialog bodies alike) and returns the
/// painted strings that still hold a 2+ letter word once content is removed:
/// exercise names, a unit symbol right after a number. Spoken-only labels
/// (`semanticLabel`, `Semantics(label:)`) are never painted, so they never
/// show up here. User-typed field values live in EditableText, not in a
/// RenderParagraph, so they are skipped too.
library;

import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/workout_plan.dart';

final _word = RegExp('[A-Za-z]{2,}');

// Unit symbols are content only when they qualify a number: "20kg",
// "1.2 km", "5 min".
final _unitAfterNumber = RegExp(r'(\d|\d\s)(kg|km|min|bpm|ms)\b');

/// Exercise names from both plans plus the test fixtures' names.
Set<String> _exerciseNames(Iterable<String> extra) => {
  for (final e in [...workoutA, ...workoutB]) e.name,
  'Squat',
  'Press',
  ...extra,
};

/// Painted strings that still contain a word after content is removed.
List<String> chromeWords(
  WidgetTester tester, {
  Iterable<String> content = const [],
}) {
  final names = _exerciseNames(content).toList()
    ..sort((a, b) => b.length.compareTo(a.length));
  final hits = <String>{};
  for (final r in tester.allRenderObjects.whereType<RenderParagraph>()) {
    final painted = r.text.toPlainText();
    var rest = painted.replaceAllMapped(_unitAfterNumber, (m) => m[1]!);
    for (final n in names) {
      rest = rest.replaceAll(n, '');
    }
    if (_word.hasMatch(rest)) hits.add(painted);
  }
  return hits.toList()..sort();
}

/// Fails with every offending string, and fails when nothing was painted
/// at all (an empty capture must never read as "clean").
void expectTextFree(
  WidgetTester tester, {
  Iterable<String> content = const [],
}) {
  final painted = tester.allRenderObjects.whereType<RenderParagraph>();
  expect(painted, isNotEmpty, reason: 'nothing painted: the guard saw no UI');
  expect(chromeWords(tester, content: content), isEmpty);
}
