import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:url_launcher_platform_interface/link.dart';
import 'package:url_launcher_platform_interface/url_launcher_platform_interface.dart';
import 'package:workout_app/models/exercise.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/services/storage_service.dart';

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

  Future<void> _pump(WidgetTester tester, Widget w) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(w);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
  }

  Widget _wrap({http.Client? httpClient}) =>
      MaterialApp(home: SettingsScreen(httpClient: httpClient));

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

  /// The GITHUB SYNC section sits below several exercises' worth of weight
  /// rows and threshold cards; `ListView` only builds elements within the
  /// viewport (+ cache extent) even for a plain `children:` list, so it must
  /// be scrolled into view before `find` can see it.
  Future<void> _scrollToGitHubSync(WidgetTester tester) async {
    await tester.scrollUntilVisible(
      find.text('Connect GitHub'),
      500,
      scrollable: find.byType(Scrollable),
    );
  }

  testWidgets('shows Settings app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Settings'), findsOneWidget);
  });

  testWidgets('shows WEIGHTS and PROGRESSION THRESHOLDS sections',
      (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('WEIGHTS'), findsOneWidget);
    expect(find.text('PROGRESSION THRESHOLDS'), findsOneWidget);
  });

  testWidgets('shows all exercise names from both workout plans', (tester) async {
    await _pump(tester, _wrap());
    for (final ex in [...workoutA, ...workoutB]) {
      expect(find.text(ex.name), findsWidgets);
    }
  });

  testWidgets('Reset defaults button is present', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Reset defaults'), findsOneWidget);
  });

  testWidgets('increment weight button increases weight', (tester) async {
    await _pump(tester, _wrap());

    final firstName = workoutA.first.name;
    final state = await StorageService.instance.getExerciseState(firstName);
    final before = state!.weight;

    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pump();

    expect(find.textContaining('${before + kWeightIncrement}kg'), findsWidgets);
  });

  testWidgets('decrement weight button decreases weight', (tester) async {
    await _pump(tester, _wrap());

    final firstName = workoutA.first.name;
    final state = await StorageService.instance.getExerciseState(firstName);
    final before = state!.weight;

    await tester.tap(find.byIcon(Icons.remove).first);
    await tester.pump();

    expect(
      find.textContaining('${before - kWeightIncrement}kg'),
      findsWidgets,
    );
  });

  testWidgets('threshold circles show values 1-5', (tester) async {
    await _pump(tester, _wrap());
    for (int i = 1; i <= 5; i++) {
      expect(find.text('$i'), findsWidgets);
    }
  });

  testWidgets('Reset dialog shows on tap and cancels', (tester) async {
    await _pump(tester, _wrap());
    await tester.tap(find.text('Reset defaults'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Reset to defaults?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Reset to defaults?'), findsNothing);
  });

  testWidgets('Reset dialog confirms and resets data', (tester) async {
    await StorageService.instance
        .setExerciseWeight(workoutA.first.name, 99.0);

    await _pump(tester, _wrap());
    await tester.tap(find.text('Reset defaults'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Reset'));
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final state =
        await StorageService.instance.getExerciseState(workoutA.first.name);
    expect(state!.weight, workoutA.first.weight);
  });

  testWidgets('shows GITHUB SYNC section with a Connect GitHub button', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await _scrollToGitHubSync(tester);
    expect(find.text('GITHUB SYNC'), findsOneWidget);
    expect(find.text('Connect GitHub'), findsOneWidget);
  });

  testWidgets(
    'shows Connected immediately when a token is already saved',
    (tester) async {
      installFakeSecureStorage(initial: {'sync.token': 'already-saved'});
      await _pump(tester, _wrap());
      await _scrollToGitHubSync(tester);
      expect(find.text('Connected.'), findsOneWidget);
    },
  );

  testWidgets('Advanced section reveals the PAT fallback field', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await _scrollToGitHubSync(tester);
    expect(find.text('Save'), findsNothing);

    await tester.tap(find.text('Advanced: paste a token instead'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(TextField, ''), findsOneWidget);
    expect(find.text('Save'), findsOneWidget);
  });

  testWidgets('saving a pasted token shows a confirmation', (tester) async {
    await _pump(tester, _wrap());
    await _scrollToGitHubSync(tester);
    await tester.tap(find.text('Advanced: paste a token instead'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.widgetWithText(ElevatedButton, 'Save'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'a-pasted-token');
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(find.text('Sync token saved.'), findsOneWidget);
  });

  testWidgets('device flow failure to start shows a message', (tester) async {
    final mock = MockClient((_) async => http.Response('nope', 422));
    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap(httpClient: mock));
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tester.pump();
      await _scrollToGitHubSync(tester);

      await tester.tap(find.text('Connect GitHub'));
      await _pumpUntil(
        tester,
        () =>
            find
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
      await _scrollToGitHubSync(tester);

      await tester.tap(find.text('Connect GitHub'));
      await _pumpUntil(
        tester,
        () => find.text('WXYZ-1234').evaluate().isNotEmpty,
      );
      expect(find.text('WXYZ-1234'), findsOneWidget);

      await _pumpUntil(
        tester,
        () =>
            find
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

  testWidgets('device dialog: failed poll shows the error and Open launches', (
    tester,
  ) async {
    final launcher = _FakeUrlLauncher();
    UrlLauncherPlatform.instance = launcher;

    // The dialog's Open button copies the code to the clipboard first;
    // there's no clipboard plugin in the test host, so stub the channel.
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async => null,
    );
    addTearDown(
      () => messenger.setMockMethodCallHandler(SystemChannels.platform, null),
    );

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
      return http.Response(
        jsonEncode({'error': 'access_denied', 'error_description': 'no'}),
        200,
      );
    });

    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap(httpClient: mock));
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tester.pump();
      await _scrollToGitHubSync(tester);

      await tester.tap(find.text('Connect GitHub'));
      await _pumpUntil(
        tester,
        () => find.text('WXYZ-1234').evaluate().isNotEmpty,
      );
      expect(find.text('WXYZ-1234'), findsOneWidget);

      await _pumpUntil(
        tester,
        () => find.textContaining('access_denied').evaluate().isNotEmpty,
      );
      expect(find.textContaining('access_denied'), findsOneWidget);

      await tester.tap(find.text('Open GitHub & copy code'));
      await tester.pump();
      expect(launcher.launched, 'https://github.com/login/device');

      await tester.tap(find.text('Cancel'));
      await tester.pump();
    });
  });
}
