/// The typed outcome of one phone->PC workout poke.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';

/// What the PC did with the poke, as far as the phone can tell.
enum PokeOutcome {
  /// Verified, ingested and credited just now.
  credited,

  /// Already in the PC's log (the sync got there first): nothing new to do.
  duplicate,

  /// A sandbox poke: verified and timed, never written or credited.
  sandbox,

  /// New to the PC, but today's workout slot was already paid (`ok:true,
  /// credited:false, duplicate:false`).
  alreadyPaidToday,

  /// Correctly signed, but the session does not count (too short, no date):
  /// HTTP 200 with `ok:false`. [PokeResult.reason] says why.
  notCounted,

  /// No usable answer: not paired, unreachable, timed out, rejected.
  failed,
}

/// One poke's result. Never null, never thrown: [reason] is always a
/// sentence a human can act on.
@immutable
class PokeResult {
  /// Creates a result.
  const PokeResult({
    required this.outcome,
    required this.reason,
    this.shutdown,
    this.gamingBudgetMinutes,
    this.roundTripMs,
  });

  /// A failure that never got a usable reply.
  const PokeResult.failed(this.reason, {this.roundTripMs})
    : outcome = PokeOutcome.failed,
      shutdown = null,
      gamingBudgetMinutes = null;

  /// Parses the PC's JSON reply. Any shape the contract does not allow is a
  /// [PokeOutcome.failed] naming what was wrong, not an exception.
  factory PokeResult.fromReply(int status, String body, int roundTripMs) {
    Object? decoded;
    FormatException? notJson;
    try {
      decoded = jsonDecode(body);
    } on FormatException catch (error) {
      // Handed on in the result; PcPokeService logs every failed result.
      notJson = error;
    }
    if (notJson != null) {
      return PokeResult.failed(
        'PC answered HTTP $status with a non-JSON body ($notJson)',
        roundTripMs: roundTripMs,
      );
    }
    if (decoded is! Map<String, dynamic>) {
      return PokeResult.failed(
        'PC answered HTTP $status with JSON that is not an object',
        roundTripMs: roundTripMs,
      );
    }
    final reason = decoded['reason'] is String
        ? decoded['reason'] as String
        : 'PC gave no reason';
    // 401/409/400/404/405/411/413/500 all carry JSON, but none of them is
    // an answer about this workout: the sync fallback covers them.
    if (status != 200) {
      return PokeResult.failed(
        'PC rejected the poke (HTTP $status): $reason',
        roundTripMs: roundTripMs,
      );
    }
    // shutdown / gaming_budget_minutes may be null (refusals): never assumed.
    final budget = decoded['gaming_budget_minutes'];
    final shutdown = decoded['shutdown'];
    final PokeOutcome outcome;
    if (decoded['ok'] != true) {
      outcome = PokeOutcome.notCounted;
    } else if (decoded['sandbox'] == true) {
      outcome = PokeOutcome.sandbox;
    } else if (decoded['duplicate'] == true) {
      outcome = PokeOutcome.duplicate;
    } else if (decoded['credited'] == true) {
      outcome = PokeOutcome.credited;
    } else {
      outcome = PokeOutcome.alreadyPaidToday;
    }
    return PokeResult(
      outcome: outcome,
      reason: reason,
      shutdown: shutdown is String ? shutdown : null,
      gamingBudgetMinutes: budget is int ? budget : null,
      roundTripMs: roundTripMs,
    );
  }

  /// What happened.
  final PokeOutcome outcome;

  /// Why, in words.
  final String reason;

  /// The PC's shutdown time after this poke, `HH:MM`.
  final String? shutdown;

  /// Today's gaming budget after this poke, in minutes.
  final int? gamingBudgetMinutes;

  /// Measured phone-side round trip, when a request was actually sent.
  final int? roundTripMs;

  /// The one line the finish screen shows for this result.
  String get label {
    switch (outcome) {
      case PokeOutcome.credited:
        final parts = <String>['PC ✓'];
        if (shutdown != null) parts.add('shutdown $shutdown');
        final minutes = gamingBudgetMinutes;
        final gaming = minutes == null
            ? ''
            : ' · gaming ${(minutes / 60).toStringAsFixed(1)}h';
        return '${parts.join(' ')}$gaming';
      case PokeOutcome.duplicate:
        return 'PC: already credited';
      case PokeOutcome.sandbox:
        return 'PC ✓ (sandbox, not credited) · ${roundTripMs ?? '?'} ms';
      case PokeOutcome.alreadyPaidToday:
        return 'PC: already credited today';
      case PokeOutcome.notCounted:
        return 'PC: not counted — $reason';
      case PokeOutcome.failed:
        return 'PC: will credit within 60 s (via sync)';
    }
  }

  @override
  String toString() =>
      'PokeResult(${outcome.name}, rtt=${roundTripMs}ms, reason: $reason)';
}
