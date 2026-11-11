import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:workout_app/models/run_record.dart';
import 'package:workout_app/models/run_track.dart';
import 'package:workout_app/services/dufs_credentials.dart';
import 'package:workout_app/services/runnerup_importer.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/tcx_codec.dart';

const String kFixtureDir = '../../screen_locker/tests/fixtures/run_tcx';

/// The three golden exports, by file name.
Map<String, Uint8List> fixtureTcx() => {
  for (final f in Directory(kFixtureDir).listSync().whereType<File>())
    if (f.path.endsWith('.tcx')) f.uri.pathSegments.last: f.readAsBytesSync(),
};

final DufsCredentials kLogin = DufsCredentials(
  url: 'https://dufs.test/',
  user: 'runnerup',
  password: 'pw',
);

Future<DufsCredentials?> fakeLogin() async => kLogin;

/// A dufs stand-in that records every request; nothing touches a network.
class FakeDufs {
  FakeDufs(this.files);

  /// `processed/` contents by name.
  final Map<String, Uint8List> files;

  /// `METHOD /path` of every request, in order.
  final List<String> requests = [];

  /// The marker bodies PUT so far.
  final List<String> markers = [];

  int listStatus = 207;
  int markerStatus = 201;
  Set<String> failingGets = {};
  bool unreachable = false;
  String? depth;

  late final MockClient client = MockClient((request) async {
    requests.add('${request.method} ${request.url.path}');
    if (unreachable) throw const SocketException('network is down');
    if (request.headers['Authorization'] != kLogin.authorization) {
      return http.Response('unauthorized', 401);
    }
    if (request.method == 'PROPFIND') {
      depth = request.headers['Depth'];
      return http.Response(
        listStatus == 207 ? multistatus(files.keys) : 'denied',
        listStatus,
      );
    }
    if (request.method == 'PUT') {
      markers.add(request.body);
      return http.Response('', markerStatus);
    }
    final name = Uri.decodeComponent(request.url.pathSegments.last);
    if (failingGets.contains(name)) return http.Response('boom', 500);
    return http.Response.bytes(files[name]!, 200);
  });

  Iterable<String> get puts => requests.where((r) => r.startsWith('PUT '));
  Iterable<String> get gets => requests.where((r) => r.startsWith('GET '));
}

/// A dufs-shaped multistatus: the collection first, then each file.
String multistatus(Iterable<String> names) =>
    '''
<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
<D:response><D:href>/RunnerUp/processed/</D:href><D:propstat><D:prop>
<D:resourcetype><D:collection/></D:resourcetype></D:prop>
<D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>
${names.map((n) => '<D:response><D:href>/RunnerUp/processed/${Uri.encodeComponent(n)}</D:href><D:propstat><D:prop><D:resourcetype></D:resourcetype></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>').join('\n')}
<D:response><D:href>/RunnerUp/processed/same.gpx</D:href></D:response>
</D:multistatus>''';

Uint8List utf8Bytes(String s) => Uint8List.fromList(utf8.encode(s));

final DateTime kNow = DateTime.utc(2026, 11, 10, 8);

RunnerUpImporter makeImporter(
  FakeDufs dufs, {
  Future<bool> Function()? canRead,
  String localDir = '/nonexistent/RunnerUp',
  bool android = true,
}) => RunnerUpImporter(
  client: dufs.client,
  loadLogin: fakeLogin,
  canReadStorage: canRead ?? () async => false,
  localDir: localDir,
  isAndroid: android,
  now: () => kNow,
);

Future<List<RunRecord>> storedRuns() => StorageService.instance.listRuns();

/// What the marker must list for [files]: every RunnerUp-authored run once
/// (a `Pixel_6a_` twin is the same run), never an app-authored file.
List<String> expectedMarkerNames(Map<String, Uint8List> files) {
  final seen = <String>{};
  return [
    for (final name in files.keys.toList()..sort())
      if (decodeTcx(utf8.decode(files[name]!), fileName: name).source ==
              RunSource.runnerupImport &&
          seen.add(name.replaceFirst('Pixel_6a_', '')))
        name,
  ];
}
