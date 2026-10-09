/// Where the PC is and the key the poke is signed with.
///
/// The key arrives over adb (`scripts/pair_phone.sh` -> `PairPcReceiver`).
/// A manifest receiver runs without a Dart isolate, so it parks the key in a
/// private no-backup file and Dart moves it into secure storage the next
/// time it asks -- at startup, in Settings, and before every poke.
library;

import 'dart:developer';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:workout_app/sandbox/sandbox_http.dart';
import 'package:workout_app/services/pc_poke_wire.dart';
import 'package:workout_app/services/storage_service.dart';

export 'package:workout_app/services/pc_poke_wire.dart' show kPcPokePort;

/// Snapshot of the pairing. [keyHex] never leaves the services layer: the
/// UI only ever reads [paired].
@immutable
class PcPairingState {
  /// Creates a snapshot.
  const PcPairingState({required this.host, this.keyHex});

  /// The PC's LAN host.
  final String host;

  /// The shared HMAC key, or null when this install is not paired.
  final String? keyHex;

  /// Whether a key is stored.
  bool get paired => keyHex != null;
}

final RegExp _hostPattern = RegExp(r'^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,252})$');

/// Whether [host] is usable as the PC address (an IPv4 or a hostname).
bool isValidPcHost(String host) => _hostPattern.hasMatch(host);

/// Reads and writes the pairing. Each package (daily, sandbox) has its own
/// keystore and database, so each has its own key slot by construction.
abstract final class PcPairing {
  /// Channel `MainActivity` answers `takePending` / `clearPending` on.
  static const MethodChannel channel = MethodChannel(
    'com.kuhy.workout_app/pc_pairing',
  );

  /// Secure-storage entry the key is kept under.
  static const String keyName = 'pc_poke_key';

  /// The keystore; tests swap the platform channel, not this.
  static const FlutterSecureStorage _secure = FlutterSecureStorage();

  static bool _channelDown = false;

  /// Absorbs any pending adb pairing, then returns the current pairing and
  /// points the sandbox's network exception at its host.
  static Future<PcPairingState> load() async {
    await absorbPending();
    final host = await StorageService.instance.getPcHost() ?? kDefaultPcHost;
    String? key;
    try {
      key = await _secure.read(key: keyName);
    } on Exception catch (error) {
      log(
        'PC pairing key unreadable ($error) -- treating as not paired',
        name: 'PcPairing',
        level: 900,
      );
    }
    SandboxHttpOverrides.pokeHost = host;
    return PcPairingState(
      host: host,
      keyHex: key != null && isValidPokeKeyHex(key) ? key : null,
    );
  }

  /// Persists the PC address the Settings field holds.
  static Future<void> saveHost(String host) async {
    await StorageService.instance.setPcHost(host);
    SandboxHttpOverrides.pokeHost = host;
  }

  /// Moves a key the receiver parked into secure storage. Returns what
  /// happened as a sentence; the parked copy is deleted only after the
  /// secure write succeeded, so a failure here loses nothing.
  static Future<String> absorbPending() async {
    if (_channelDown) return 'no pairing channel on this platform';
    Map<Object?, Object?>? pending;
    try {
      pending = await channel.invokeMapMethod<Object?, Object?>('takePending');
    } on MissingPluginException catch (error) {
      _channelDown = true;
      log(
        'no pairing channel ($error) -- adb pairing is Android-only',
        name: 'PcPairing',
        level: 900,
      );
      return 'no pairing channel on this platform';
    } on PlatformException catch (error) {
      log('reading the parked pairing failed: $error', level: 1000);
      return 'reading the parked pairing failed: $error';
    }
    if (pending == null) return 'nothing pending';
    final key = pending['key'];
    final host = pending['host'];
    if (key is! String || !isValidPokeKeyHex(key)) {
      log('parked pairing key is malformed -- discarded', level: 1000);
      await channel.invokeMethod<void>('clearPending');
      return 'parked pairing key is malformed';
    }
    try {
      await _secure.write(key: keyName, value: key.toLowerCase());
    } on PlatformException catch (error) {
      log('storing the pairing key failed: $error', level: 1000);
      return 'storing the pairing key failed: $error';
    }
    if (host is String && isValidPcHost(host)) {
      await saveHost(host);
    }
    await channel.invokeMethod<void>('clearPending');
    log('PC pairing absorbed from adb', name: 'PcPairing', level: 800);
    return 'paired';
  }

  /// Forgets a failed channel so the next call retries it.
  @visibleForTesting
  static void resetForTesting() => _channelDown = false;
}
