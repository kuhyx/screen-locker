/// The WebDAV half of the RunnerUp history import: list, fetch, marker PUT.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:workout_app/services/dufs_credentials.dart';
import 'package:xml/xml.dart';

/// Folder on the PC that holds the already-handled RunnerUp exports.
const String kRunnerUpProcessedPath = '/RunnerUp/processed/';

/// The ONE file the app ever writes to the PC for the import: the
/// import-complete marker.
///
/// A dotfile at the top of `/RunnerUp` is invisible to `runnerup_watch.sh`
/// (it skips names starting with '.') and to every `*.tcx` glob, so it can
/// never be credited as a workout. [putImportMarker] is the importer's only
/// PUT and its path is this constant, never built from a file name.
const String kImportMarkerPath = '/RunnerUp/.workout_app_import.json';

/// Per-request ceiling, so a half-open connection cannot hang the import.
const Duration kDavTimeout = Duration(seconds: 20);

/// A request the server did not answer with success.
class DavException implements Exception {
  /// Creates the exception.
  const DavException(this.what);

  /// A sentence naming the request and why it failed.
  final String what;

  @override
  String toString() => what;
}

/// The `.tcx` file names directly inside `/RunnerUp/processed/`.
///
/// One PROPFIND with `Depth: 1`. Throws [DavException] on a non-multistatus
/// answer (401 included) and an `XmlException` on unreadable XML.
Future<List<String>> listProcessedTcx(
  http.Client client,
  DufsCredentials login,
) async {
  final request = http.Request(
    'PROPFIND',
    Uri.parse('${login.url}$kRunnerUpProcessedPath'),
  )..headers.addAll({'Authorization': login.authorization, 'Depth': '1'});
  final response = await _send(client, request);
  if (response.statusCode != 207) {
    throw DavException(
      'PROPFIND $kRunnerUpProcessedPath answered ${response.statusCode}',
    );
  }
  return tcxNamesFromMultistatus(utf8.decode(response.bodyBytes));
}

/// The `.tcx` basenames named by the `href`s of a multistatus [xml].
///
/// Hrefs may be absolute paths or full URLs and are percent-encoded; the
/// collection itself (a trailing slash) has no name and is skipped.
List<String> tcxNamesFromMultistatus(String xml) {
  final names = <String>{};
  for (final href in XmlDocument.parse(
    xml,
  ).descendantElements.where((e) => e.localName == 'href')) {
    final path = Uri.decodeFull(Uri.parse(href.innerText.trim()).path);
    final name = path.substring(path.lastIndexOf('/') + 1);
    if (name.toLowerCase().endsWith('.tcx') && !name.startsWith('.')) {
      names.add(name);
    }
  }
  return names.toList()..sort();
}

/// Downloads one export from `/RunnerUp/processed/` as raw bytes (the caller
/// decides what a non-UTF-8 file means).
Future<Uint8List> fetchProcessedTcx(
  http.Client client,
  DufsCredentials login,
  String name,
) async {
  final request = http.Request(
    'GET',
    Uri.parse(
      '${login.url}$kRunnerUpProcessedPath${Uri.encodeComponent(name)}',
    ),
  )..headers['Authorization'] = login.authorization;
  final response = await _send(client, request);
  if (response.statusCode != 200) {
    throw DavException('GET $name answered ${response.statusCode}');
  }
  return response.bodyBytes;
}

/// PUTs [body] to [kImportMarkerPath]; throws [DavException] unless 2xx.
Future<void> putImportMarker(
  http.Client client,
  DufsCredentials login,
  String body,
) async {
  final request =
      http.Request('PUT', Uri.parse('${login.url}$kImportMarkerPath'))
        ..headers.addAll({
          'Authorization': login.authorization,
          'Content-Type': 'application/json',
        })
        ..body = body;
  final response = await _send(client, request);
  if (response.statusCode < 200 || response.statusCode > 299) {
    throw DavException(
      'PUT $kImportMarkerPath answered ${response.statusCode}',
    );
  }
}

Future<http.Response> _send(http.Client client, http.Request request) async {
  final streamed = await client.send(request).timeout(kDavTimeout);
  return await http.Response.fromStream(streamed);
}
