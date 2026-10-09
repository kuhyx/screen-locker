// The PC address the workout poke is sent to.
//
// A `part` of StorageService for the same reason as the sandbox part: it
// needs `_getSetting`, and one setting does not earn a second storage layer.
// The key itself is NOT here -- it lives in secure storage (pc_pairing.dart).
part of 'storage_service.dart';

/// Settings key the PC host is stored under.
const String kPcHostKey = 'pc_host';

/// Persistence for the PC link.
extension StorageServicePcLink on StorageService {
  /// The saved PC host, or null when the default should be used.
  Future<String?> getPcHost() => _getSetting(kPcHostKey);

  /// Persists the PC host.
  Future<void> setPcHost(String host) => _setSetting(kPcHostKey, host);
}
