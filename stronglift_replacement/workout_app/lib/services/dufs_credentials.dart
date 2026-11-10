/// Login for the PC's dufs WebDAV server (`/RunnerUp`, scoped read-write).
///
/// One shared definition so the run uploader and the RunnerUp history
/// importer read the very same secure-storage slots; provisioned once from a
/// `dufs_login.json` that carries `url`, `user` and `password`.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Secure-storage key of [DufsCredentials.url].
const String kDufsUrlKey = 'dufs_url';

/// Secure-storage key of [DufsCredentials.user].
const String kDufsUserKey = 'dufs_user';

/// Secure-storage key of [DufsCredentials.password].
const String kDufsPasswordKey = 'dufs_password';

/// Where the PC's dufs is and who to log in as.
@immutable
class DufsCredentials {
  /// Creates a login; trailing slashes of [url] are dropped so
  /// `'$url/RunnerUp/...'` is always well formed.
  DufsCredentials({
    required String url,
    required this.user,
    required this.password,
  }) : url = url.replaceFirst(RegExp(r'/+$'), '');

  /// Parses a `dufs_login.json` document; null when a field is missing.
  static DufsCredentials? fromJson(Map<String, dynamic> json) {
    final url = json['url'];
    final user = json['user'];
    final password = json['password'];
    if (url is! String || user is! String || password is! String) return null;
    if (url.isEmpty || user.isEmpty || password.isEmpty) return null;
    return DufsCredentials(url: url, user: user, password: password);
  }

  /// The origin, e.g. `https://kuhy-cloud.duckdns.org` (no trailing slash).
  final String url;

  /// The Basic-auth user.
  final String user;

  /// The Basic-auth password.
  final String password;

  /// The `Authorization` header value.
  String get authorization =>
      'Basic ${base64Encode(utf8.encode('$user:$password'))}';

  /// The stored login, or null when any of the three slots is empty.
  static Future<DufsCredentials?> load({
    FlutterSecureStorage storage = const FlutterSecureStorage(),
  }) async {
    final url = await storage.read(key: kDufsUrlKey);
    final user = await storage.read(key: kDufsUserKey);
    final password = await storage.read(key: kDufsPasswordKey);
    return fromJson({'url': url, 'user': user, 'password': password});
  }

  /// Stores this login.
  Future<void> save({
    FlutterSecureStorage storage = const FlutterSecureStorage(),
  }) async {
    await storage.write(key: kDufsUrlKey, value: url);
    await storage.write(key: kDufsUserKey, value: user);
    await storage.write(key: kDufsPasswordKey, value: password);
  }
}
