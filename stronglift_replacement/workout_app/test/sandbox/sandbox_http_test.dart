import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/sandbox/sandbox_http.dart';

void main() {
  final printed = <String>[];
  setUp(() {
    printed.clear();
    debugPrint = (String? message, {int? wrapWidth}) => printed.add(message ?? '');
  });
  tearDown(() => debugPrint = debugPrintThrottled);

  test('refuses every connection before a socket is opened', () async {
    final client = SandboxHttpOverrides().createHttpClient(null);
    // Thrown from inside getUrl itself: the refusal happens before any
    // request object exists, let alone a socket.
    await expectLater(
      () async => client.getUrl(Uri.parse('http://firebase.example.invalid/x')),
      throwsA(isA<SocketException>()),
    );
    expect(printed.single, contains('refused network connection to firebase.example.invalid'));
    client.close(force: true);
  });
}
