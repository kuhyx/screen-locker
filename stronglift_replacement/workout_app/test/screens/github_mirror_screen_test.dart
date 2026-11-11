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
import '../icon_finders.dart';

/// The token field: the one whose prefix icon is labelled 'GitHub PAT'.
final _patField = find.ancestor(
  of: iconLabeled('GitHub PAT'),
  matching: find.byType(TextField),
);

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

  testWidgets('shows the app bar and Connect GitHub', (tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    expect(iconLabeled('Advanced sync (GitHub)'), findsOneWidget);
    expect(iconLabeled('Connect GitHub'), findsOneWidget);
  });

  testWidgets('a saved token is VERIFIED on open, not blindly trusted', (
    tester,
  ) async {
    // Regression: the badge used to read "Connected." whenever a token
    // string existed, so a revoked token showed green while every sync
    // 401'd and history silently stayed empty.
    installFakeSecureStorage(initial: {'sync.token': 'revoked-token'});
    final mock = MockClient(
      (req) async => http.Response('Bad credentials', 401),
    );
    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap(httpClient: mock));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    expect(find.bySemanticsLabel('Connected.'), findsNothing);
    expect(
      find.bySemanticsLabel(RegExp(RegExp.escape('NOT connected'))),
      findsOneWidget,
    );
  });

  testWidgets('a saved token that GitHub accepts reports verified', (
    tester,
  ) async {
    installFakeSecureStorage(initial: {'sync.token': 'good-token'});
    final mock = MockClient(
      (req) async => http.Response(
        jsonEncode({'content': base64Encode(utf8.encode('{}')), 'sha': 's'}),
        200,
      ),
    );
    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap(httpClient: mock));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    expect(
      find.bySemanticsLabel(
        RegExp(RegExp.escape('Connected and verified via GitHub')),
      ),
      findsOneWidget,
    );
  });

  testWidgets('the PAT fallback field is present', (tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    expect(iconLabeled('Save'), findsOneWidget);
    expect(_patField, findsOneWidget);
  });

  testWidgets('saving a pasted token shows a confirmation', (tester) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap());
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    await tester.enterText(_patField, 'a-pasted-token');
    await tester.tap(iconLabeled('Save'));
    await tester.pump();
    expect(find.bySemanticsLabel('Sync token saved.'), findsOneWidget);
  });
}
