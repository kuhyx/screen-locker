import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:url_launcher_platform_interface/link.dart';
import 'package:url_launcher_platform_interface/url_launcher_platform_interface.dart';
import 'package:workout_app/screens/github_mirror_screen.dart';
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/storage_service.dart';
import 'package:workout_app/services/sync_settings.dart';
import 'package:workout_app/ui/theme.dart';

import '../fake_secure_storage.dart';

/// Stub launcher that records the URL instead of opening it, so the device
/// dialog's "Open GitHub & copy code" can be exercised without a real
/// platform channel.
class _FakeUrlLauncher extends UrlLauncherPlatform
    with MockPlatformInterfaceMixin {
  String? launched;

  @override
  final LinkDelegate? linkDelegate = null;

  @override
  Future<bool> supportsMode(PreferredLaunchMode mode) async => true;

  @override
  Future<bool> launchUrl(String url, LaunchOptions options) async {
    launched = url;
    return true;
  }
}

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  setUp(() async {
    StorageService.resetForTesting();
    await StorageService.init();
    installFakeSecureStorage();
  });

  Widget _wrap({http.Client? httpClient}) => MaterialApp(
    theme: buildAppTheme(),
    home: GitHubMirrorScreen(httpClient: httpClient),
  );

  /// Drains the device flow's real `Future.delayed` poll (GitHubDeviceAuth
  /// injects no test delay, so under `runAsync` it is a genuine Timer, not
  /// the fake-clock one `tester.pump(duration)` advances) by interleaving
  /// real waits with frame pumps until [done] is true or [maxTries] is hit.
  Future<void> _pumpUntil(
    WidgetTester tester,
    bool Function() done, {
    int maxTries = 200,
  }) async {
    for (var i = 0; i < maxTries && !done(); i++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await tester.pump();
    }
  }

  testWidgets('device flow failure to start shows a message', (tester) async {
    final mock = MockClient((_) async => http.Response('nope', 422));
    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap(httpClient: mock));
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tester.pump();

      await tester.tap(find.text('Connect GitHub'));
      await _pumpUntil(
        tester,
        () => find
            .textContaining('Could not start device flow')
            .evaluate()
            .isNotEmpty,
      );

      expect(
        find.textContaining('Could not start device flow'),
        findsOneWidget,
      );
    });
  });

  testWidgets('device flow happy path saves and verifies the token', (
    tester,
  ) async {
    final mock = MockClient((req) async {
      if (req.url.path.contains('device/code')) {
        return http.Response(
          jsonEncode({
            'device_code': 'dev123',
            'user_code': 'WXYZ-1234',
            'verification_uri': 'https://github.com/login/device',
            'interval': 0,
            'expires_in': 900,
          }),
          200,
        );
      }
      if (req.url.path.contains('oauth/access_token')) {
        return http.Response(jsonEncode({'access_token': 'gho_test'}), 200);
      }
      // The post-connect verification GET on devices/phone/log.json.
      return http.Response(
        jsonEncode({'content': base64Encode(utf8.encode('{}'))}),
        200,
      );
    });

    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap(httpClient: mock));
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tester.pump();

      await tester.tap(find.text('Connect GitHub'));
      await _pumpUntil(
        tester,
        () => find.text('WXYZ-1234').evaluate().isNotEmpty,
      );
      expect(find.text('WXYZ-1234'), findsOneWidget);

      await _pumpUntil(
        tester,
        () => find
            .textContaining('Connected and verified via GitHub')
            .evaluate()
            .isNotEmpty,
      );

      expect(
        find.textContaining('Connected and verified via GitHub'),
        findsOneWidget,
      );
    });
  });
}
