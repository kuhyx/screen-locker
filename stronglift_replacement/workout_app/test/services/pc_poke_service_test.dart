// PcPokeService against a fake PC: signing, every failure shape, and the
// bounded budget. Plain `test()` so `.timeout()` runs on real timers.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/exercise_result.dart';
import 'package:workout_app/models/set_result.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/pc_pairing.dart';
import 'package:workout_app/services/pc_poke_service.dart';
import 'package:workout_app/services/pc_poke_wire.dart';

final String _keyHex = 'a1' * 32;

WorkoutSession _session() {
  final start = DateTime(2026, 10, 9, 7, 30);
  return WorkoutSession(
    workoutType: 'A',
    startTime: start,
    endTime: start.add(const Duration(minutes: 40)),
    exercises: [
      ExerciseResult(
        exercise: const Exercise(name: 'Squat', sets: 1, reps: 5, weight: 60),
        sets: [SetResult(targetReps: 5, doneReps: 5, weight: 60)],
      ),
    ],
  );
}

/// A MockClient that records whether it was closed.
class _ClosingClient extends MockClient {
  _ClosingClient(super.fn);

  bool closed = false;

  @override
  void close() {
    closed = true;
    super.close();
  }
}

String _reply({
  bool ok = true,
  bool credited = false,
  bool sandbox = false,
  Object? shutdown,
  Object? gaming,
  String reason = 'fine',
}) => jsonEncode({
  'ok': ok,
  'credited': credited,
  'duplicate': false,
  'sandbox': sandbox,
  'shutdown': shutdown,
  'gaming_budget_minutes': gaming,
  'reason': reason,
});

PcPokeService _service(
  http.Client client, {
  String? keyHex,
  bool? sandbox,
  Future<PcPairingState> Function()? pairing,
  Duration timeout = const Duration(seconds: 2),
}) => PcPokeService(
  clientFactory: () => client,
  pairingLoader:
      pairing ??
      () async => PcPairingState(host: '10.0.0.7', keyHex: keyHex ?? _keyHex),
  clock: () => DateTime.fromMillisecondsSinceEpoch(1760000000000),
  nonce: () => 'nonce-1',
  sandboxOverride: sandbox,
  timeout: timeout,
);

void main() {
  test('signs the exact body bytes and parses a credited reply', () async {
    late http.Request seen;
    final client = _ClosingClient((request) async {
      seen = request;
      return http.Response(
        _reply(credited: true, shutdown: '22:00', gaming: 120),
        200,
      );
    });
    final result = await _service(client, sandbox: false).poke(_session());

    expect(result.outcome, PokeOutcome.credited);
    expect(result.label, 'PC ✓ shutdown 22:00 · gaming 2.0h');
    expect(result.roundTripMs, isNotNull);
    expect(seen.url.toString(), 'http://10.0.0.7:$kPcPokePort$kPcPokePath');
    expect(
      seen.headers[kPcPokeSignatureHeader],
      signPokeBody(decodePokeKeyHex(_keyHex), seen.bodyBytes),
    );
    final body = jsonDecode(utf8.decode(seen.bodyBytes)) as Map;
    expect(body['record_id'], _session().startTime.toIso8601String());
    expect(body['sandbox'], isFalse);
    expect(body['nonce'], 'nonce-1');
    expect(body['sent_at_ms'], 1760000000000);
    expect(client.closed, isTrue);
  });

  test('a sandbox poke is flagged and reads back as sandbox', () async {
    late Map<String, dynamic> body;
    final client = MockClient((request) async {
      body = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response(_reply(sandbox: true), 200);
    });
    final result = await _service(client, sandbox: true).poke(_session());
    expect(body['sandbox'], isTrue);
    expect(result.outcome, PokeOutcome.sandbox);
    expect(result.label, startsWith('PC ✓ (sandbox, not credited) · '));
  });

  test('null shutdown and budget are carried as null, not guessed', () async {
    final client = MockClient(
      (_) async => http.Response(_reply(credited: true), 200),
    );
    final result = await _service(client).poke(_session());
    expect(result.shutdown, isNull);
    expect(result.gamingBudgetMinutes, isNull);
    expect(result.label, 'PC ✓');
  });

  test('a 200 ok:false is "not counted" with the PC reason', () async {
    final client = MockClient(
      (_) async => http.Response(_reply(ok: false, reason: 'too short'), 200),
    );
    final result = await _service(client).poke(_session());
    expect(result.outcome, PokeOutcome.notCounted);
    expect(result.label, 'PC: not counted — too short');
  });

  test('a non-200 falls back to the sync line', () async {
    final client = MockClient(
      (_) async => http.Response(_reply(ok: false, reason: 'bad mac'), 401),
    );
    final result = await _service(client).poke(_session());
    expect(result.outcome, PokeOutcome.failed);
    expect(result.reason, contains('HTTP 401'));
    expect(result.label, 'PC: will credit within 60 s (via sync)');
  });

  test('a connection reset is a failure with the cause, not a throw', () async {
    final client = _ClosingClient(
      (_) async => throw http.ClientException('Connection reset by peer'),
    );
    final result = await _service(client).poke(_session());
    expect(result.outcome, PokeOutcome.failed);
    expect(result.reason, contains('could not reach the PC'));
    expect(result.reason, contains('Connection reset by peer'));
    expect(client.closed, isTrue);
  });

  test('a refused socket is a failure too', () async {
    final client = MockClient(
      (_) async => throw const SocketException('Connection refused'),
    );
    final result = await _service(client).poke(_session());
    expect(result.reason, contains('Connection refused'));
  });

  test('a PC that never answers is cut off and its socket closed', () async {
    final never = Completer<http.Response>();
    final client = _ClosingClient((_) => never.future);
    final result = await _service(
      client,
      timeout: const Duration(milliseconds: 50),
    ).poke(_session());
    expect(result.outcome, PokeOutcome.failed);
    expect(result.reason, 'no reply from the PC within 50 ms');
    // Timer and Stopwatch clocks differ by a millisecond either way.
    expect(result.roundTripMs, inInclusiveRange(40, 1000));
    expect(client.closed, isTrue);
  });

  test('a hanging keystore counts against the same budget', () async {
    final client = _ClosingClient((_) async => http.Response('{}', 200));
    final result = await _service(
      client,
      pairing: () => Completer<PcPairingState>().future,
      timeout: const Duration(milliseconds: 30),
    ).poke(_session());
    expect(result.reason, 'no reply from the PC within 30 ms');
    expect(client.closed, isFalse, reason: 'no client was ever built');
  });

  test('an unpaired phone never sends anything', () async {
    var sent = false;
    final client = MockClient((_) async {
      sent = true;
      return http.Response('{}', 200);
    });
    final result = await _service(
      client,
      pairing: () async => const PcPairingState(host: '10.0.0.7'),
    ).poke(_session());
    expect(sent, isFalse);
    expect(result.reason, contains('not paired'));
    expect(result.roundTripMs, isNull);
  });
}
