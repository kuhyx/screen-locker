import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/google_sign_in_backend.dart';

const _channel = MethodChannel('dev.kuhy/google_account_token');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_channel, null);
  });

  group('googleIdToken', () {
    test('returns the token the sign-in function yields', () async {
      // The injected path: proves the closure is what feeds crdt_sync, and
      // that no platform channel is touched to get there.
      expect(
        await googleIdToken(signInFn: () async => 'a-token'),
        'a-token',
      );
    });

    test('passes a null cancellation straight through', () async {
      // Dismissing the picker is an ordinary outcome, not an error: the
      // caller falls back to the password path.
      expect(await googleIdToken(signInFn: () async => null), isNull);
    });

    test('reports "not configured" when the client id is missing', () async {
      // An empty id must not reach the OS account chooser.
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(await googleIdToken(serverClientId: ''), isNull);
    });

    test('warns loudly when the client id is empty', () async {
      final warnings = <String>[];
      expect(
        await googleIdToken(serverClientId: '', warn: warnings.add),
        isNull,
      );
      expect(warnings, hasLength(1));
      expect(warnings.single, contains('kServerClientId'));
    });

    test('logs via dart:developer when no warn hook is given', () async {
      // Default path (no seam): must not throw and must still return null.
      expect(await googleIdToken(serverClientId: ''), isNull);
    });

    test('asks the account-token plugin for the Web client id', () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      Object? sent;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(_channel, (call) async {
            sent = call.arguments;
            return 'plugin-token';
          });
      expect(await googleIdToken(), 'plugin-token');
      expect(sent, {'serverClientId': kServerClientId});
    });

    test('pins the uid the security rules expect', () {
      // If this ever drifts from database.rules.json, a Google sign-in would
      // be accepted here and then denied every read and write.
      expect(kSyncUid, 'OvA2REQyLIhAHOEjzwS1o877rgG3');
    });
  });

  group('googleSignInSupported', () {
    test('is true on Android', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      expect(googleSignInSupported, isTrue);
    });

    test('is false on Linux desktop, so the password path stays', () {
      debugDefaultTargetPlatformOverride = TargetPlatform.linux;
      expect(googleSignInSupported, isFalse);
    });
  });
}
