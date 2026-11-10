import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/sandbox/sandbox_http.dart';
import 'package:workout_app/services/pc_poke_wire.dart';

void main() {
  final printed = <String>[];
  setUp(() {
    printed.clear();
    debugPrint = (String? message, {int? wrapWidth}) =>
        printed.add(message ?? '');
  });
  tearDown(() {
    debugPrint = debugPrintThrottled;
    SandboxHttpOverrides.pokeHost = null;
  });

  test('refuses every connection before a socket is opened', () async {
    final client = SandboxHttpOverrides().createHttpClient(null);
    // Thrown from inside getUrl itself: the refusal happens before any
    // request object exists, let alone a socket.
    await expectLater(
      () async => client.getUrl(Uri.parse('http://firebase.example.invalid/x')),
      throwsA(isA<SocketException>()),
    );
    expect(
      printed.single,
      contains('refused network connection to firebase.example.invalid'),
    );
    client.close(force: true);
  });

  group('the one PC-poke exception', () {
    const host = '127.0.0.1';
    final poke = Uri.parse('http://$host:$kPcPokePort$kPcPokePath');

    test('allows nothing until a PC host is configured', () {
      expect(SandboxHttpOverrides.allows(poke), isFalse);
    });

    test('allows exactly http + configured host + 8774 + /v1/workout', () {
      SandboxHttpOverrides.pokeHost = host;
      expect(SandboxHttpOverrides.allows(poke), isTrue);
      for (final other in [
        poke.replace(scheme: 'https'),
        poke.replace(host: '127.0.0.2'),
        poke.replace(port: 443),
        poke.replace(path: '/v1/other'),
        Uri.parse('https://firebaseio.com/x.json'),
      ]) {
        expect(SandboxHttpOverrides.allows(other), isFalse, reason: '$other');
      }
    });

    test('https to the same host and port is still refused', () async {
      SandboxHttpOverrides.pokeHost = host;
      final client = SandboxHttpOverrides().createHttpClient(null);
      await expectLater(
        () async =>
            client.postUrl(Uri.parse('https://$host:$kPcPokePort$kPcPokePath')),
        throwsA(isA<SocketException>()),
      );
      expect(printed.single, contains('refused network connection to $host'));
      client.close(force: true);
    });

    test('another host is still refused', () async {
      SandboxHttpOverrides.pokeHost = host;
      final client = SandboxHttpOverrides().createHttpClient(null);
      await expectLater(
        () async => client.postUrl(
          Uri.parse('http://10.0.0.9:$kPcPokePort$kPcPokePath'),
        ),
        throwsA(isA<SocketException>()),
      );
      expect(
        printed.single,
        contains('refused network connection to 10.0.0.9'),
      );
      client.close(force: true);
    });

    test('the poke itself reaches the socket layer', () async {
      SandboxHttpOverrides.pokeHost = host;
      final client = SandboxHttpOverrides().createHttpClient(null);
      Object outcome = 'connected';
      try {
        // Nothing is sent: the request is opened, never written.
        final request = await client.postUrl(poke);
        request.abort();
      } on SocketException catch (error) {
        outcome = error;
      }
      // No listener on this host's poke port is fine -- what matters is that a
      // refusal, if any, did not come from the sandbox.
      if (outcome is SocketException) {
        expect(outcome.message, isNot(contains('sandbox')));
      }
      expect(
        printed.first,
        contains('allowing the PC poke to $host:$kPcPokePort'),
      );
      client.close(force: true);
    });
  });

  group('the OSM tile exception', () {
    Uri tile([
      String path = '/17/70123/42650.png',
      String host = 'tile.openstreetmap.org',
    ]) => Uri.parse('https://$host$path');

    test('allows https tiles on the one host, zoom 0 to 19', () {
      for (final path in [
        '/0/0/0.png',
        '/9/1/2.png',
        '/17/70123/42650.png',
        '/19/1/2.png',
      ]) {
        expect(
          SandboxHttpOverrides.allowsTile(tile(path)),
          isTrue,
          reason: path,
        );
      }
    });

    test('refuses everything else, including look-alike hosts', () {
      for (final other in [
        tile('/20/1/2.png'),
        tile('/17/1/2.png?x=1'),
        tile('/17/1/2.jpg'),
        tile('/'),
        tile('/api/0.6/map'),
        tile('/17/1/2.png', 'a.tile.openstreetmap.org'),
        tile('/17/1/2.png', 'openstreetmap.org'),
        tile('/17/1/2.png', 'tile.openstreetmap.org.evil.example'),
        tile('/17/1/2.png').replace(scheme: 'http', port: 80),
        tile('/17/1/2.png').replace(port: 8443),
        Uri.parse('https://kuhy-cloud.duckdns.org/x.json'),
      ]) {
        expect(
          SandboxHttpOverrides.allowsTile(other),
          isFalse,
          reason: '$other',
        );
      }
    });

    test('a tile reaches the socket layer, not the sandbox refusal', () async {
      final client = SandboxHttpOverrides().createHttpClient(null);
      Object outcome = 'connected';
      try {
        final request = await client.getUrl(tile());
        request.abort();
      } on SocketException catch (error) {
        outcome = error;
      }
      if (outcome is SocketException) {
        expect(outcome.message, isNot(contains('sandbox')));
      }
      expect(printed.first, contains('allowing OSM tile /17/70123/42650.png'));
      client.close(force: true);
    });

    test('kuhy-cloud and a tile-looking path elsewhere stay refused', () async {
      final client = SandboxHttpOverrides().createHttpClient(null);
      for (final uri in [
        Uri.parse('https://kuhy-cloud.duckdns.org/17/1/2.png'),
        Uri.parse('https://kuhy-cloud.duckdns.org/x.json'),
      ]) {
        await expectLater(
          () => client.getUrl(uri),
          throwsA(isA<SocketException>()),
        );
      }
      expect(printed, hasLength(2));
      expect(
        printed.first,
        contains('refused network connection to kuhy-cloud.duckdns.org'),
      );
      client.close(force: true);
    });

    test('the PC poke is unchanged next to the tile exception', () {
      SandboxHttpOverrides.pokeHost = '127.0.0.1';
      final poke = Uri.parse('http://127.0.0.1:$kPcPokePort$kPcPokePath');
      expect(SandboxHttpOverrides.allows(poke), isTrue);
      expect(SandboxHttpOverrides.allowsTile(poke), isFalse);
      expect(SandboxHttpOverrides.allows(tile()), isFalse);
    });
  });
}
