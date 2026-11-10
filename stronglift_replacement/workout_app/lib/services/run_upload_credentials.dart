/// Where finished runs are uploaded, and the login for it.
///
/// The login is a dufs account scoped to the PC's `/RunnerUp` folder. It is
/// never typed on the phone: `scripts/provision_run_upload.sh` pushes a
/// `dufs_login.json` into the app's external files directory, and
/// [RunCredentialStore.importProvisionFile] moves it into secure storage and
/// deletes the file.
library;

import 'dart:convert';
import 'dart:developer';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path_provider/path_provider.dart';
import 'package:workout_app/services/dufs_credentials.dart';

/// File name the provisioning script pushes.
const String kProvisionFileName = 'dufs_login.json';

/// What an import attempt found.
enum ProvisionStatus {
  /// No file: the normal case on every start after the first.
  absent,

  /// Login stored and the file deleted.
  imported,

  /// A file was there but unusable; it was left in place.
  invalid,
}

/// Result of [RunCredentialStore.importProvisionFile].
@immutable
class ProvisionOutcome {
  /// Creates an outcome.
  const ProvisionOutcome(this.status, this.reason);

  /// What happened.
  final ProvisionStatus status;

  /// A sentence saying why.
  final String reason;
}

Future<Directory?> _externalFilesDir() async {
  // coverage:ignore-start
  // Android-only plugin call; path_provider throws on every other platform.
  if (Platform.isAndroid) return await getExternalStorageDirectory();
  // coverage:ignore-end
  return null;
}

/// Imports the upload login into secure storage (the slots of
/// [DufsCredentials], shared with the history importer).
class RunCredentialStore {
  /// Creates a store; the arguments are test seams.
  RunCredentialStore({
    this._secure = const FlutterSecureStorage(),
    this._externalDir = _externalFilesDir,
  });

  final FlutterSecureStorage _secure;
  final Future<Directory?> Function() _externalDir;

  /// The stored login, or null when none was provisioned yet.
  Future<DufsCredentials?> read() => DufsCredentials.load(storage: _secure);

  /// Moves `<external files dir>/dufs_login.json` into secure storage and
  /// deletes it. An unusable file stays put and is reported, so a typo in the
  /// script's output cannot silently leave uploads switched off.
  Future<ProvisionOutcome> importProvisionFile() async {
    final dir = await _externalDir();
    if (dir == null) {
      return const ProvisionOutcome(
        ProvisionStatus.absent,
        'no external files directory on this platform',
      );
    }
    final file = File('${dir.path}/$kProvisionFileName');
    if (!file.existsSync()) {
      return const ProvisionOutcome(ProvisionStatus.absent, 'no login file');
    }
    final login = _parse(await file.readAsString());
    if (login == null) {
      const reason =
          '$kProvisionFileName is not {"url","user","password"} with an '
          'http(s) url, so run uploads stay switched off. Re-run '
          'scripts/provision_run_upload.sh.';
      log('RunCredentialStore: $reason', level: 1000);
      return const ProvisionOutcome(ProvisionStatus.invalid, reason);
    }
    await login.save(storage: _secure);
    await file.delete();
    log('RunCredentialStore: imported the run-upload login for ${login.user}.');
    return ProvisionOutcome(
      ProvisionStatus.imported,
      'imported the login for ${login.user}',
    );
  }

  DufsCredentials? _parse(String text) {
    final Object? decoded;
    try {
      decoded = jsonDecode(text);
    } on FormatException catch (error) {
      log('RunCredentialStore: $kProvisionFileName is not JSON ($error)');
      return null;
    }
    if (decoded is! Map<String, dynamic>) return null;
    final login = DufsCredentials.fromJson(decoded);
    final uri = login == null ? null : Uri.tryParse(login.url);
    if (uri == null || !uri.hasAuthority) return null;
    return const {'http', 'https'}.contains(uri.scheme) ? login : null;
  }
}
