// Maps every PC reply shape the poke contract allows onto the finish line.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/pc_poke_result.dart';

String _reply({
  bool ok = true,
  bool credited = false,
  bool duplicate = false,
  bool sandbox = false,
  String? shutdown = '21:00',
  int? gaming = 90,
  String reason = 'because',
}) => jsonEncode({
  'ok': ok,
  'credited': credited,
  'duplicate': duplicate,
  'sandbox': sandbox,
  'shutdown': shutdown,
  'gaming_budget_minutes': gaming,
  'pc_ms': 3,
  'reason': reason,
});

void main() {
  test('credited shows shutdown and gaming hours', () {
    final r = PokeResult.fromReply(200, _reply(credited: true), 40);
    expect(r.outcome, PokeOutcome.credited);
    expect(r.label, 'PC ✓ shutdown 21:00 · gaming 1.5h');
  });

  test('credited with null shutdown/budget still renders', () {
    final r = PokeResult.fromReply(
      200,
      _reply(credited: true, shutdown: null, gaming: null),
      40,
    );
    expect(r.label, 'PC ✓');
  });

  test('duplicate, already-paid and sandbox replies', () {
    expect(
      PokeResult.fromReply(200, _reply(duplicate: true), 1).label,
      'PC: already credited',
    );
    expect(
      PokeResult.fromReply(200, _reply(), 1).label,
      'PC: already credited today',
    );
    expect(
      PokeResult.fromReply(200, _reply(sandbox: true), 25).label,
      'PC ✓ (sandbox, not credited) · 25 ms',
    );
  });

  test('200 ok:false is "not counted" with the PC reason', () {
    final r = PokeResult.fromReply(
      200,
      _reply(ok: false, reason: 'session too short', shutdown: null),
      1,
    );
    expect(r.outcome, PokeOutcome.notCounted);
    expect(r.label, 'PC: not counted — session too short');
  });

  test('every non-200 status falls back to the sync line', () {
    for (final status in [400, 401, 404, 405, 409, 411, 413, 500]) {
      final r = PokeResult.fromReply(
        status,
        _reply(ok: false, shutdown: null, gaming: null, reason: 'nope'),
        1,
      );
      expect(r.outcome, PokeOutcome.failed, reason: 'HTTP $status');
      expect(r.label, 'PC: will credit within 60 s (via sync)');
      expect(r.reason, contains('HTTP $status'));
    }
  });

  test('non-JSON and non-object bodies fail with a reason', () {
    expect(PokeResult.fromReply(200, '<html>', 1).reason, contains('non-JSON'));
    expect(PokeResult.fromReply(200, '[1]', 1).reason, contains('not an'));
  });

  test('toString names the outcome, round trip and reason', () {
    expect(
      const PokeResult.failed('down', roundTripMs: 12).toString(),
      'PokeResult(failed, rtt=12ms, reason: down)',
    );
  });
}
