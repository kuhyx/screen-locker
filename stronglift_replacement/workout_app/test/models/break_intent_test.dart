import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/models/break_intent.dart';

void main() {
  group('BreakIntentKind.tryParse', () {
    test('round-trips every kind by name', () {
      for (final kind in BreakIntentKind.values) {
        expect(BreakIntentKind.tryParse(kind.name), kind);
      }
    });

    test('returns null for anything else', () {
      expect(BreakIntentKind.tryParse('finishWorkout'), isNull);
      expect(BreakIntentKind.tryParse(''), isNull);
    });
  });

  group('BreakIntent', () {
    const intent = BreakIntent(
      seq: 7,
      kind: BreakIntentKind.minusRep,
      exIdx: 1,
      setIdx: 2,
      tsMs: 1789432100123,
    );

    test('survives an encode/decode round trip', () {
      final decoded = BreakIntent.tryDecode(intent.encode())!;
      expect(decoded.seq, 7);
      expect(decoded.kind, BreakIntentKind.minusRep);
      expect(decoded.exIdx, 1);
      expect(decoded.setIdx, 2);
      expect(decoded.tsMs, 1789432100123);
      expect(decoded.toString(), contains('#7'));
    });

    // Total rather than throwing: one bad entry must not wedge the drain loop
    // and swallow every press behind it.
    test('returns null for anything it cannot read', () {
      const cases = <String>[
        'not json at all',
        '[]',
        '"a string"',
        '{"seq":"7","kind":"done","exIdx":0,"setIdx":0,"tsMs":1}',
        '{"seq":7,"kind":7,"exIdx":0,"setIdx":0,"tsMs":1}',
        '{"seq":7,"kind":"done","exIdx":"x","setIdx":0,"tsMs":1}',
        '{"seq":7,"kind":"done","exIdx":0,"setIdx":null,"tsMs":1}',
        '{"seq":7,"kind":"done","exIdx":0,"setIdx":0,"tsMs":"x"}',
        '{"seq":7,"kind":"nope","exIdx":0,"setIdx":0,"tsMs":1}',
        '{"kind":"done","exIdx":0,"setIdx":0,"tsMs":1}',
      ];
      for (final raw in cases) {
        expect(BreakIntent.tryDecode(raw), isNull, reason: raw);
      }
    });
  });
}
