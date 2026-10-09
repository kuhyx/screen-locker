// PcPairing: the adb-parked key moves into secure storage, and only then is
// the parked copy deleted -- a failure anywhere loses nothing.
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:workout_app/sandbox/sandbox_http.dart';
import 'package:workout_app/services/pc_pairing.dart';
import 'package:workout_app/services/pc_poke_wire.dart';
import 'package:workout_app/services/storage_service.dart';

import '../fake_secure_storage.dart';

final String _key = 'b2' * 32;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late List<String> calls;

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    PcPairing.resetForTesting();
    calls = [];
  });

  tearDown(() {
    SandboxHttpOverrides.pokeHost = null;
    messenger.setMockMethodCallHandler(PcPairing.channel, null);
  });

  /// Answers `takePending` with [pending] (or throws [error]) and records
  /// every call.
  void parked(Map<String, String>? pending, {Exception? error}) {
    messenger.setMockMethodCallHandler(PcPairing.channel, (call) async {
      calls.add(call.method);
      if (call.method != 'takePending') return null;
      if (error != null) throw error;
      return pending;
    });
  }

  Future<String?> storedKey() =>
      const FlutterSecureStorage().read(key: PcPairing.keyName);

  test('nothing parked: default host, not paired, sandbox host set', () async {
    installFakeSecureStorage();
    parked(null);
    final state = await PcPairing.load();
    expect(state.host, kDefaultPcHost);
    expect(state.paired, isFalse);
    expect(SandboxHttpOverrides.pokeHost, kDefaultPcHost);
    expect(calls, ['takePending']);
  });

  test('a parked key is stored lowercase, host saved, then cleared', () async {
    installFakeSecureStorage();
    parked({'key': _key.toUpperCase(), 'host': '192.168.1.50'});
    expect(await PcPairing.absorbPending(), 'paired');
    expect(calls, ['takePending', 'clearPending']);
    expect(await storedKey(), _key);

    final state = await PcPairing.load();
    expect(state.host, '192.168.1.50');
    expect(state.keyHex, _key);
    expect(state.paired, isTrue);
  });

  test('an invalid parked host is ignored, the key still pairs', () async {
    installFakeSecureStorage();
    parked({'key': _key, 'host': '-bad host'});
    expect(await PcPairing.absorbPending(), 'paired');
    expect(await StorageService.instance.getPcHost(), isNull);
  });

  test('a malformed parked key is discarded, never stored', () async {
    installFakeSecureStorage();
    parked({'key': 'nope'});
    expect(await PcPairing.absorbPending(), 'parked pairing key is malformed');
    expect(calls, ['takePending', 'clearPending']);
    expect(await storedKey(), isNull);
  });

  test('a failed secure write keeps the parked copy', () async {
    installFakeSecureStorage(throwing: true);
    parked({'key': _key});
    final outcome = await PcPairing.absorbPending();
    expect(outcome, startsWith('storing the pairing key failed'));
    expect(calls, ['takePending'], reason: 'clearPending must not run');
  });

  test('an unreadable parked file is reported, not thrown', () async {
    installFakeSecureStorage();
    parked(null, error: PlatformException(code: 'pairing_unreadable'));
    final outcome = await PcPairing.absorbPending();
    expect(outcome, startsWith('reading the parked pairing failed'));
  });

  test('no channel (desktop): said once, then not asked again', () async {
    installFakeSecureStorage();
    // No handler: the call raises MissingPluginException.
    expect(await PcPairing.absorbPending(), 'no pairing channel on this platform');
    parked(null);
    expect(await PcPairing.absorbPending(), 'no pairing channel on this platform');
    expect(calls, isEmpty);
  });

  test('a corrupt stored key reads as not paired', () async {
    installFakeSecureStorage(initial: {PcPairing.keyName: 'garbage'});
    parked(null);
    expect((await PcPairing.load()).paired, isFalse);
  });

  test('a keystore that throws reads as not paired', () async {
    installFakeSecureStorage(throwing: true);
    parked(null);
    final state = await PcPairing.load();
    expect(state.paired, isFalse);
    expect(state.host, kDefaultPcHost);
  });

  test('saveHost persists and moves the sandbox exception', () async {
    await PcPairing.saveHost('pc.lan');
    expect(await StorageService.instance.getPcHost(), 'pc.lan');
    expect(SandboxHttpOverrides.pokeHost, 'pc.lan');
  });

  test('isValidPcHost accepts IPv4 and hostnames only', () {
    expect(isValidPcHost('192.168.1.43'), isTrue);
    expect(isValidPcHost('pc.lan'), isTrue);
    expect(isValidPcHost(''), isFalse);
    expect(isValidPcHost('-x'), isFalse);
    expect(isValidPcHost('a b'), isFalse);
    expect(isValidPcHost('http://x'), isFalse);
  });
}
