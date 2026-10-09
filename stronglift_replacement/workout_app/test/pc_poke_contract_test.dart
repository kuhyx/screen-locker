// The phone half of the cross-language contract check for the workout poke.
//
// `contracts/workout_poke_v1.json` (screen-locker repo root) is a literal key,
// body and signature the Python receiver is tested against too. Each side's
// own round-trip test would pass while the two disagreed; this one cannot.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/pc_poke_wire.dart';

/// Relative to the package root, which is `flutter test`'s cwd.
const _fixturePath = '../../contracts/workout_poke_v1.json';

void main() {
  final fixture =
      jsonDecode(File(_fixturePath).readAsStringSync()) as Map<String, dynamic>;
  final keyHex = fixture['key_hex'] as String;
  final body = fixture['body_utf8'] as String;
  final expected = fixture['signature_hex'] as String;

  test('signer reproduces the shared fixture signature byte for byte', () {
    expect(signPokeBody(decodePokeKeyHex(keyHex), utf8.encode(body)), expected);
  });

  test('the fixture key is a valid pairing key', () {
    expect(isValidPokeKeyHex(keyHex), isTrue);
  });

  test('buildPokeBody emits the fixture body byte for byte', () {
    // Float (100.0, 7020.5), key order and raw non-ASCII are where encoders
    // differ. The PC never re-serializes, so this is not required for the MAC
    // to verify -- it pins that the phone's body looks like the documented one.
    final reparsed = jsonDecode(body) as Map<String, dynamic>;
    final rebuilt = buildPokeBody(
      sentAtMs: reparsed['sent_at_ms'] as int,
      nonce: reparsed['nonce'] as String,
      sandbox: reparsed['sandbox'] as bool,
      recordId: reparsed['record_id'] as String,
      payload: reparsed['payload'] as Map<String, dynamic>,
    );
    expect(utf8.decode(rebuilt), body);
  });

  test('malformed keys are rejected before they can sign', () {
    expect(isValidPokeKeyHex('ab' * 31), isFalse);
    expect(isValidPokeKeyHex('zz' * 32), isFalse);
    expect(() => decodePokeKeyHex('nope'), throwsFormatException);
  });
}
