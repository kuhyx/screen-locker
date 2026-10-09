/// Sends a finished workout straight to the PC so the credit lands in under
/// a second instead of waiting for the sync round trip.
library;

import 'dart:async';
import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:uuid/uuid.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/sandbox/sandbox.dart';
import 'package:workout_app/sandbox/sandbox_log.dart';
import 'package:workout_app/services/pc_pairing.dart';
import 'package:workout_app/services/pc_poke_result.dart';
import 'package:workout_app/services/pc_poke_wire.dart';
import 'package:workout_app/services/workout_sync_service.dart';

export 'package:workout_app/services/pc_poke_result.dart';

/// Signs and POSTs one session to `http://<pc-host>:8773/v1/workout`.
///
/// Runs beside [WorkoutSyncService.push], never instead of it: the PC dedups
/// by record id, so whichever path lands first credits and the other is a
/// duplicate. Off the home LAN this fails fast and the sync is the only path.
class PcPokeService {
  /// Creates a service. Every collaborator is injectable so tests need no
  /// network, keystore or clock.
  PcPokeService({
    http.Client Function()? clientFactory,
    Future<PcPairingState> Function()? pairingLoader,
    DateTime Function()? clock,
    String Function()? nonce,
    this.sandboxOverride,
    this.timeout = const Duration(seconds: 2),
  }) : _clientFactory = clientFactory ?? IOClient.new,
       _pairingLoader = pairingLoader ?? PcPairing.load,
       _clock = clock ?? DateTime.now,
       _nonce = nonce ?? const Uuid().v4;

  /// A fresh client per call, so it is built under whatever `HttpOverrides`
  /// are current (the sandbox's narrow exception included).
  final http.Client Function() _clientFactory;
  final Future<PcPairingState> Function() _pairingLoader;
  final DateTime Function() _clock;
  final String Function() _nonce;

  /// Forces the body's `sandbox` flag; null follows [Sandbox.enabled].
  final bool? sandboxOverride;

  /// Budget for the whole poke, key load included. Past it the finish screen
  /// says the sync will credit instead.
  final Duration timeout;

  /// Pokes the PC with [session]. Never throws; failures log at warning.
  Future<PokeResult> poke(WorkoutSession session) async {
    final watch = Stopwatch()..start();
    http.Client? client;
    // Set by the catch below and reported (at warning) right after it.
    Exception failure;
    try {
      final pairing = await _pairingLoader().timeout(timeout);
      final keyHex = pairing.keyHex;
      if (keyHex == null) {
        return _report(
          const PokeResult.failed(
            'this phone is not paired with the PC -- run '
            'scripts/pair_phone.sh there; the sync will credit meanwhile',
          ),
        );
      }
      final sandbox = sandboxOverride ?? Sandbox.enabled;
      final body = buildPokeBody(
        sentAtMs: _clock().millisecondsSinceEpoch,
        nonce: _nonce(),
        sandbox: sandbox,
        recordId: workoutRecordId(session),
        payload: workoutRecordPayload(session),
      );
      final signature = signPokeBody(decodePokeKeyHex(keyHex), body);
      final uri = Uri(
        scheme: 'http',
        host: pairing.host,
        port: kPcPokePort,
        path: kPcPokePath,
      );
      client = _clientFactory();
      final left = timeout - watch.elapsed;
      final response = await client
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              kPcPokeSignatureHeader: signature,
            },
            body: body,
          )
          .timeout(left.isNegative ? Duration.zero : left);
      return _report(
        PokeResult.fromReply(
          response.statusCode,
          response.body,
          watch.elapsedMilliseconds,
        ),
      );
    } on Exception catch (error) {
      failure = error;
    } finally {
      // Closing aborts a request the timeout gave up on, so a dead PC never
      // keeps a socket open behind the finish screen.
      client?.close();
    }
    return _report(
      PokeResult.failed(
        failure is TimeoutException
            ? 'no reply from the PC within ${timeout.inMilliseconds} ms'
            : 'could not reach the PC: $failure',
        roundTripMs: watch.elapsedMilliseconds,
      ),
    );
  }

  /// Logs every result -- a poke that fails says so at warning level, never
  /// silently -- and mirrors it into the sandbox trace.
  PokeResult _report(PokeResult result) {
    final failed =
        result.outcome == PokeOutcome.failed ||
        result.outcome == PokeOutcome.notCounted;
    final line =
        'PC poke ${result.outcome.name} in ${result.roundTripMs ?? '-'} ms: '
        '${result.reason}';
    log(line, name: 'PcPoke', level: failed ? 900 : 800);
    debugPrint('WorkoutApp: $line');
    SandboxLog.event('pc poke', {
      'outcome': result.outcome.name,
      'rtt_ms': result.roundTripMs,
      'reason': result.reason,
    });
    return result;
  }
}
