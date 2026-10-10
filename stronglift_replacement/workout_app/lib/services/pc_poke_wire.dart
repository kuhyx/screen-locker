/// Wire format of the phone->PC workout poke (v1).
///
/// Binding spec: `docs/DOCS-workout-poke-contract.md` at the screen-locker
/// repo root, with the literal fixture `contracts/workout_poke_v1.json` that
/// both this file and the Python receiver are tested against. Pure Dart, no
/// Flutter: the contract test loads it without a binding.
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// TCP port the PC's poke listener binds (8771 and 8773 -- book-guard's
/// desktop wrapper -- belong to other services).
const int kPcPokePort = 8774;

/// Request path on the PC.
const String kPcPokePath = '/v1/workout';

/// Header carrying `hex(HMAC-SHA256(key, raw body bytes))`.
const String kPcPokeSignatureHeader = 'X-Poke-Signature';

/// Wire-format version this phone speaks.
const int kPcPokeVersion = 1;

/// The PC's static LAN address; the Settings field starts here.
const String kDefaultPcHost = '192.168.1.43';

final RegExp _keyHex = RegExp(r'^[0-9a-fA-F]{64}$');

/// Whether [text] is a pairing key: exactly 32 bytes as 64 hex characters.
bool isValidPokeKeyHex(String text) => _keyHex.hasMatch(text);

/// Decodes a key accepted by [isValidPokeKeyHex]; throws [FormatException]
/// on anything else so a malformed key can never sign a request.
Uint8List decodePokeKeyHex(String keyHex) {
  if (!isValidPokeKeyHex(keyHex)) {
    throw const FormatException('pairing key must be exactly 64 hex chars');
  }
  final out = Uint8List(32);
  for (var i = 0; i < 32; i++) {
    out[i] = int.parse(keyHex.substring(i * 2, i * 2 + 2), radix: 16);
  }
  return out;
}

/// `hex(HMAC-SHA256(key, bodyBytes))` over the bytes exactly as sent.
String signPokeBody(List<int> key, List<int> bodyBytes) =>
    Hmac(sha256, key).convert(bodyBytes).toString();

/// Serializes the request body ONCE; the caller signs and sends these exact
/// bytes. Key order follows the contract for readability only -- the PC
/// verifies the MAC over the received bytes and never re-serializes.
Uint8List buildPokeBody({
  required int sentAtMs,
  required String nonce,
  required bool sandbox,
  required String recordId,
  required Map<String, dynamic> payload,
}) => utf8.encode(
  jsonEncode({
    'v': kPcPokeVersion,
    'sent_at_ms': sentAtMs,
    'nonce': nonce,
    'sandbox': sandbox,
    'record_id': recordId,
    'payload': payload,
  }),
);
