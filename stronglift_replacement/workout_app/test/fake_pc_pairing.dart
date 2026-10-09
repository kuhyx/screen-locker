import 'package:workout_app/services/pc_pairing.dart';

/// A settled, unpaired pairing for screens that only need the PC LINK
/// section to render: no pairing channel, keystore or database involved, and
/// `SandboxHttpOverrides.pokeHost` stays untouched.
Future<PcPairingState> fakePcPairing() async =>
    const PcPairingState(host: '10.0.0.2');
