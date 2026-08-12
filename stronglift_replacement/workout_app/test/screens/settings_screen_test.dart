import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
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
import 'package:workout_app/services/backup_service.dart';
import 'package:workout_app/services/sync_settings.dart';
import 'package:workout_app/models/workout_plan.dart';
import 'package:workout_app/screens/settings_screen.dart';
import 'package:workout_app/services/progression_sync_service.dart';
import 'package:workout_app/services/storage_service.dart';
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

  Future<void> _pump(WidgetTester tester, Widget w) async {
    await tester.runAsync(() async {
      await tester.pumpWidget(w);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();
  }

  Widget _wrap({
    http.Client? httpClient,
    Future<FirebaseRestClient?> Function()? firebaseFactory,
    Future<FirebaseRestClient?> Function()? googleFirebaseFactory,
    bool? googleAvailable,
    Future<FirebaseAccount?> Function()? accountLoader,
    Future<void> Function(FirebaseAccount)? accountSaver,
    Future<void> Function()? accountClearer,
    Future<bool> Function()? sessionProbe,
    Future<bool> Function()? storageChecker,
    Future<bool> Function()? storageRequester,
    Future<ProgressionSyncResult> Function()? progressionPuller,
  }) => MaterialApp(
    theme: buildAppTheme(),
    home: SettingsScreen(
      httpClient: httpClient,
      // Injected so the widget never reaches the OS keystore, which
      // `flutter test` has no platform-channel binding for.
      firebaseFactory: firebaseFactory ?? () async => null,
      googleFirebaseFactory: googleFirebaseFactory,
      googleAvailable: googleAvailable,
      accountLoader: accountLoader ?? () async => null,
      accountSaver: accountSaver,
      accountClearer: accountClearer,
      // Defaults to whatever the injected account says, so a test that only
      // stubs the account still describes one coherent device. The production
      // probe reads the keystore this harness deliberately avoids, and would
      // otherwise answer "no session" for a device the test declared signed
      // in.
      sessionProbe:
          sessionProbe ??
          () async => await (accountLoader ?? () async => null)() != null,
      // Same reason: permission_handler is a platform channel too.
      storageChecker: storageChecker ?? () async => false,
      storageRequester: storageRequester,
      // Default to a no-op pull: connecting triggers one, and the real service
      // would open a database and hit the network from a widget test.
      progressionPuller:
          progressionPuller ??
          () async => const ProgressionSyncResult(
            changed: false,
            reason: 'stubbed in tests',
          ),
    ),
  );

  /// Expands the "Advanced (GitHub mirror)" section.
  ///
  /// GitHub is the cutover mirror rather than a choice the user makes, so
  /// everything GitHub-facing -- the connect button and the PAT fallback --
  /// is collapsed by default.
  Future<void> openAdvanced(WidgetTester tester) async {
    // The ListView builds lazily, so the tile has to be scrolled into the
    // viewport before it exists to tap. Name the outer Scrollable: once the
    // tile is built there is more than one.
    await tester.scrollUntilVisible(
      find.text('Advanced (GitHub mirror)'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Advanced (GitHub mirror)'));
    await tester.pumpAndSettle();
  }

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
    // Scroll to the SYNC header rather than "Connect GitHub": the latter now
    // lives inside a collapsed disclosure, and once that tile is built there
    // is more than one Scrollable, so the finder must name the outer list.
    await tester.scrollUntilVisible(
      find.text('Advanced (GitHub mirror)'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
  }

  testWidgets('shows Settings app bar', (tester) async {
    await _pump(tester, _wrap());
    expect(find.text('Settings'), findsOneWidget);
  });

  testWidgets('shows WEIGHTS, TARGET REPS and PROGRESSION THRESHOLDS', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    expect(find.text('WEIGHTS'), findsOneWidget);
    // TARGET REPS and the thresholds below it are off-screen at the test
    // viewport height, so scroll them into view rather than asserting on
    // whatever happens to be built.
    await tester.scrollUntilVisible(find.text('TARGET REPS'), 200);
    expect(find.text('TARGET REPS'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('PROGRESSION THRESHOLDS'), 200);
    expect(find.text('PROGRESSION THRESHOLDS'), findsOneWidget);
  });

  testWidgets('increment reps button increases the target reps', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await tester.scrollUntilVisible(find.text('TARGET REPS'), 200);
    await tester.pumpAndSettle();
    // Situp defaults to 30 reps and is the only exercise at that value.
    expect(find.text('30 reps'), findsOneWidget);
    final plus = find.descendant(
      of: find.ancestor(
        of: find.text('30 reps'),
        matching: find.byType(Row),
      ).first,
      matching: find.byIcon(Icons.add),
    );
    await tester.tap(plus);
    await tester.pumpAndSettle();
    expect(find.text('31 reps'), findsOneWidget);
  });

  testWidgets('shows all exercise names from both workout plans', (
    tester,
  ) async {
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
    // DB reads need the real event loop (the widget-test zone fakes async).
    final state = await tester.runAsync(
      () => StorageService.instance.getExerciseState(firstName),
    );
    final before = state!.weight;

    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pump();

    expect(find.textContaining('${before + kWeightIncrement}kg'), findsWidgets);
  });

  testWidgets('decrement weight button decreases weight', (tester) async {
    await _pump(tester, _wrap());

    final firstName = workoutA.first.name;
    // DB reads need the real event loop (the widget-test zone fakes async).
    final state = await tester.runAsync(
      () => StorageService.instance.getExerciseState(firstName),
    );
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
    // The threshold cards sit below WEIGHTS and TARGET REPS, past the test
    // viewport's fold, so they are not built until scrolled to.
    await tester.scrollUntilVisible(find.text('PROGRESSION THRESHOLDS'), 200);
    await tester.pumpAndSettle();
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
    await tester.runAsync(
      () =>
          StorageService.instance.setExerciseWeight(workoutA.first.name, 99.0),
    );

    await _pump(tester, _wrap());
    await tester.tap(find.text('Reset defaults'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Reset'));
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final state = await tester.runAsync(
      () => StorageService.instance.getExerciseState(workoutA.first.name),
    );
    expect(state!.weight, workoutA.first.weight);
  });

  testWidgets('Connect Firebase with empty fields asks for credentials', (
    tester,
  ) async {
    var saved = false;
    await _pump(tester, _wrap(accountSaver: (_) async => saved = true));
    await _scrollToGitHubSync(tester);

    await tester.ensureVisible(find.text('Connect Firebase'));
    await tester.pump();
    await tester.tap(find.text('Connect Firebase'));
    await tester.pump();

    expect(
      find.textContaining('Enter the sync account email and password'),
      findsOneWidget,
    );
    expect(saved, isFalse);
  });

  testWidgets('Connect Firebase stores the account and reports success', (
    tester,
  ) async {
    FirebaseAccount? saved;
    await _pump(
      tester,
      _wrap(
        accountSaver: (a) async => saved = a,
        firebaseFactory: () async => _stubFirebaseClient(),
      ),
    );
    await _scrollToGitHubSync(tester);

    await tester.enterText(
      find.widgetWithText(TextField, 'Sync account email'),
      'sync@example.com',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Sync account password'),
      'pw',
    );
    await tester.ensureVisible(find.text('Connect Firebase'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Connect Firebase'));
    await tester.pumpAndSettle();

    // saveAccount must actually be called: without it openFirebase() reads an
    // account nothing ever wrote, and Firebase is a silent no-op forever.
    expect(saved?.email, 'sync@example.com');
    expect(find.text('Connected to Firebase.'), findsOneWidget);
    expect(find.text('sync@example.com'), findsOneWidget);
  });

  testWidgets(
    'Sign in with Google connects and reads back the persisted account',
    (tester) async {
      var sessionStored = false;
      await _pump(
        tester,
        _wrap(
          googleAvailable: true,
          googleFirebaseFactory: () async {
            sessionStored = true;
            return _stubFirebaseClient();
          },
          accountLoader: () async => sessionStored
              ? const FirebaseAccount(email: 'g@example.com', password: '')
              : null,
        ),
      );
      await _scrollToGitHubSync(tester);

      await tester.ensureVisible(find.text('Sign in with Google'));
      await tester.pump();
      await tester.tap(find.text('Sign in with Google'));
      await tester.pumpAndSettle();

      expect(find.text('Connected to Firebase.'), findsOneWidget);
      expect(find.text('g@example.com'), findsOneWidget);
    },
  );

  testWidgets(
    'Sign in with Google reports a cancelled picker as pending, not an error',
    (tester) async {
      await _pump(
        tester,
        _wrap(googleAvailable: true, googleFirebaseFactory: () async => null),
      );
      await _scrollToGitHubSync(tester);

      await tester.ensureVisible(find.text('Sign in with Google'));
      await tester.pump();
      await tester.tap(find.text('Sign in with Google'));
      await tester.pump();
      await tester.pump();

      expect(find.text('Google sign-in was cancelled.'), findsOneWidget);
    },
  );

  testWidgets(
    'Sign in with Google that does not persist a session reports the retry '
    'message',
    (tester) async {
      await _pump(
        tester,
        _wrap(
          googleAvailable: true,
          googleFirebaseFactory: () async => _stubFirebaseClient(),
          sessionProbe: () async => false,
        ),
      );
      await _scrollToGitHubSync(tester);

      await tester.ensureVisible(find.text('Sign in with Google'));
      await tester.pump();
      await tester.tap(find.text('Sign in with Google'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('did not save the session'),
        findsOneWidget,
      );
    },
  );

  testWidgets('Sign in with Google wrong-account error surfaces the message', (
    tester,
  ) async {
    await _pump(
      tester,
      _wrap(
        googleAvailable: true,
        googleFirebaseFactory: () async =>
            throw FirebaseAuthError('wrong uid'),
      ),
    );
    await _scrollToGitHubSync(tester);

    await tester.ensureVisible(find.text('Sign in with Google'));
    await tester.pump();
    await tester.tap(find.text('Sign in with Google'));
    await tester.pumpAndSettle();

    expect(find.text('wrong uid'), findsOneWidget);
  });

  testWidgets('Sign in with Google generic failure surfaces the error text', (
    tester,
  ) async {
    await _pump(
      tester,
      _wrap(
        googleAvailable: true,
        googleFirebaseFactory: () async => throw StateError('boom'),
      ),
    );
    await _scrollToGitHubSync(tester);

    await tester.ensureVisible(find.text('Sign in with Google'));
    await tester.pump();
    await tester.tap(find.text('Sign in with Google'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Google sign-in failed'), findsOneWidget);
  });

  testWidgets('connecting pulls progression down immediately', (tester) async {
    // Regression: connecting is the NORMAL path after a reinstall, because the
    // uninstall wipes the keystore and startup's pull therefore found no
    // account. Without pulling here the device sits on factory defaults while
    // holding real remote progression, and its first finished workout pushes
    // those defaults over the top.
    var pulled = false;
    await _pump(
      tester,
      _wrap(
        firebaseFactory: () async => _stubFirebaseClient(),
        progressionPuller: () async {
          pulled = true;
          return const ProgressionSyncResult(
            changed: true,
            count: 7,
            reason: 'restored 7 exercise(s) from Firebase',
          );
        },
      ),
    );
    await _scrollToGitHubSync(tester);

    await tester.enterText(
      find.widgetWithText(TextField, 'Sync account email'),
      'sync@example.com',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Sync account password'),
      'pw',
    );
    await tester.ensureVisible(find.text('Connect Firebase'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Connect Firebase'));
    await tester.pumpAndSettle();

    expect(pulled, isTrue);
    expect(
      find.text('Connected. Restored 7 exercise(s) from Firebase.'),
      findsOneWidget,
    );
  });

  testWidgets('a rejected account is cleared rather than left half-stored', (
    tester,
  ) async {
    var cleared = false;
    await _pump(
      tester,
      _wrap(
        accountSaver: (_) async {},
        accountClearer: () async => cleared = true,
        firebaseFactory: () async => null,
      ),
    );
    await _scrollToGitHubSync(tester);

    await tester.enterText(
      find.widgetWithText(TextField, 'Sync account email'),
      'wrong@example.com',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Sync account password'),
      'bad',
    );
    await tester.ensureVisible(find.text('Connect Firebase'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Connect Firebase'));
    await tester.pumpAndSettle();

    expect(cleared, isTrue);
    expect(find.text('Firebase rejected that account.'), findsOneWidget);
  });

  testWidgets('a stored account shows as connected, and disconnects', (
    tester,
  ) async {
    var cleared = false;
    await _pump(
      tester,
      _wrap(
        accountLoader: () async =>
            const FirebaseAccount(email: 'stored@example.com', password: 'pw'),
        accountClearer: () async => cleared = true,
      ),
    );
    await _scrollToGitHubSync(tester);

    expect(find.text('stored@example.com'), findsOneWidget);

    // Explicit pumps, not pumpAndSettle: the token-verification path this
    // screen kicks off on open keeps a timer alive, so settling never
    // completes (same pitfall the device-flow tests work around).
    await tester.ensureVisible(find.text('Disconnect'));
    await tester.pump();
    await tester.tap(find.text('Disconnect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(cleared, isTrue);
    expect(find.text('Firebase disconnected.'), findsOneWidget);
  });

  testWidgets('offline backup offers a grant button when not held', (
    tester,
  ) async {
    var asked = false;
    await _pump(
      tester,
      _wrap(
        storageChecker: () async => false,
        storageRequester: () async {
          asked = true;
          return true;
        },
      ),
    );
    await tester.scrollUntilVisible(
      find.text('Grant storage permission'),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    // Framed as optional: Firebase restores progression without it.
    expect(
      find.textContaining('Optional.', skipOffstage: false),
      findsOneWidget,
    );

    await tester.tap(find.text('Grant storage permission'));
    await tester.pumpAndSettle();

    expect(asked, isTrue, reason: 'the grant page is opened on demand only');
    expect(find.text('Storage permission granted'), findsOneWidget);
    expect(find.text('Grant storage permission'), findsNothing);
  });

  testWidgets('offline backup reports an already-granted permission', (
    tester,
  ) async {
    await _pump(tester, _wrap(storageChecker: () async => true));
    await tester.scrollUntilVisible(
      find.text('Storage permission granted'),
      500,
      scrollable: find.byType(Scrollable).first,
    );

    expect(find.text('Storage permission granted'), findsOneWidget);
    expect(find.text('Grant storage permission'), findsNothing);
    expect(find.textContaining('Granted.', skipOffstage: false), findsOneWidget);
  });

  testWidgets('leads with Firebase and hides GitHub behind Advanced', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await _scrollToGitHubSync(tester);

    // GitHub is the cutover mirror, not a peer choice.
    //
    // `SYNC` is found with a scroll-independent finder: the OFFLINE BACKUP
    // section added below `Advanced (GitHub mirror)` made the page taller, so
    // scrolling that tile into view now pushes the SYNC header off the top.
    // What this test asserts is the ORDER (Firebase leads, GitHub is hidden),
    // not that both happen to fit on screen at once.
    expect(find.text('SYNC', skipOffstage: false), findsOneWidget);
    expect(
      find.text('Connect Firebase', skipOffstage: false),
      findsOneWidget,
    );
    expect(find.text('Connect GitHub'), findsNothing);

    await openAdvanced(tester);
    expect(find.text('Connect GitHub'), findsOneWidget);
  });

  testWidgets(
    'a saved token is VERIFIED on open, not blindly trusted',
    (tester) async {
      // Regression: the badge used to read "Connected." whenever a token
      // string existed, so a revoked token showed green while every sync
      // 401'd and history silently stayed empty.
      installFakeSecureStorage(initial: {'sync.token': 'revoked-token'});
      final mock = MockClient(
        (req) async => http.Response('Bad credentials', 401),
      );
      await _pump(tester, _wrap(httpClient: mock));
      await _scrollToGitHubSync(tester);
      expect(find.text('Connected.'), findsNothing);
      expect(find.textContaining('NOT connected'), findsOneWidget);
    },
  );

  testWidgets(
    'a saved token that GitHub accepts reports verified',
    (tester) async {
      installFakeSecureStorage(initial: {'sync.token': 'good-token'});
      final mock = MockClient(
        (req) async => http.Response(
          jsonEncode({'content': base64Encode(utf8.encode('{}')), 'sha': 's'}),
          200,
        ),
      );
      await _pump(tester, _wrap(httpClient: mock));
      await _scrollToGitHubSync(tester);
      expect(
        find.textContaining('Connected and verified via GitHub'),
        findsOneWidget,
      );
    },
  );

  testWidgets('Advanced section reveals the PAT fallback field', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await _scrollToGitHubSync(tester);
    expect(find.text('Save'), findsNothing);

    await openAdvanced(tester);

    // The Firebase email/password fields are empty too, so scope the
    // assertion to the PAT field's own Save button instead of counting
    // empty TextFields.
    expect(find.text('Save'), findsOneWidget);
  });

  testWidgets('saving a pasted token shows a confirmation', (tester) async {
    await _pump(tester, _wrap());
    await _scrollToGitHubSync(tester);
    await openAdvanced(tester);
    await tester.ensureVisible(find.widgetWithText(ElevatedButton, 'Save'));
    await tester.pumpAndSettle();

    // Three TextFields exist now (Firebase email/password + the PAT), so
    // pick the PAT field by its hint rather than by type.
    await tester.enterText(
      find.widgetWithText(TextField, 'GitHub PAT'),
      'a-pasted-token',
    );
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

      await openAdvanced(tester);
      await tester.ensureVisible(find.text('Connect GitHub'));
      await tester.pumpAndSettle();
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
      await _scrollToGitHubSync(tester);

      await openAdvanced(tester);
      await tester.ensureVisible(find.text('Connect GitHub'));
      await tester.pumpAndSettle();
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

      await openAdvanced(tester);
      await tester.ensureVisible(find.text('Connect GitHub'));
      await tester.pumpAndSettle();
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

  testWidgets('changing a success threshold persists it', (tester) async {
    await _pump(tester, _wrap());
    // Scroll to the section header first: the threshold rows below it are not
    // built at all until then, so a `.first` finder for the label would throw
    // "Bad state: No element" before it could match anything.
    await tester.scrollUntilVisible(find.text('PROGRESSION THRESHOLDS'), 200);
    await tester.pumpAndSettle();
    final label = find.text('↑ Increase after N successes').first;
    await tester.scrollUntilVisible(
      label,
      300,
      scrollable: find.byType(Scrollable),
    );
    // The circles (1-5) live in the same Row as the label; tap the "5" circle.
    final row = find.ancestor(of: label, matching: find.byType(Row)).first;
    final five = find.descendant(of: row, matching: find.text('5')).first;
    // The row can sit below the 800x600 test fold — bring the circle fully in.
    await tester.ensureVisible(five);
    await tester.pumpAndSettle();
    // _onThresholdChanged awaits a DB write, so drive it on the real loop.
    await tester.runAsync(() async {
      await tester.tap(five);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final states = await tester.runAsync(
      () => StorageService.instance.getAllExerciseStates(),
    );
    expect(states!.any((s) => s.successThreshold == 5), isTrue);

    // Also exercise the fail-threshold path (onFailChanged closure).
    final failLabel = find.text('↓ Decrease after N failures').first;
    await tester.ensureVisible(failLabel);
    await tester.pumpAndSettle();
    final failRow = find
        .ancestor(of: failLabel, matching: find.byType(Row))
        .first;
    final failFour = find
        .descendant(of: failRow, matching: find.text('4'))
        .first;
    await tester.ensureVisible(failFour);
    await tester.pumpAndSettle();
    await tester.runAsync(() async {
      await tester.tap(failFour);
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pump();

    final states2 = await tester.runAsync(
      () => StorageService.instance.getAllExerciseStates(),
    );
    expect(states2!.any((s) => s.failThreshold == 4), isTrue);
  });

  testWidgets('reps change is debounced then written to storage', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    await tester.scrollUntilVisible(find.text('TARGET REPS'), 200);
    await tester.pumpAndSettle();

    // Situp defaults to 30 reps and is the only exercise at that value.
    final minus = find.descendant(
      of: find
          .ancestor(of: find.text('30 reps'), matching: find.byType(Row))
          .first,
      matching: find.byIcon(Icons.remove),
    );
    // Same 600ms debounce as weights: run on the real loop so the timer fires.
    await tester.runAsync(() async {
      await tester.tap(minus);
      await Future<void>.delayed(const Duration(milliseconds: 800));
    });
    await tester.pump();

    final after = (await tester.runAsync(
      () => StorageService.instance.getExerciseState('Situp'),
    ))!.reps;
    expect(after, 29, reason: 'the decrement must reach storage');
  });

  testWidgets('weight change is debounced then written to storage', (
    tester,
  ) async {
    await _pump(tester, _wrap());
    final name = workoutA.first.name;
    final before = (await tester.runAsync(
      () => StorageService.instance.getExerciseState(name),
    ))!.weight;

    // Tapping "+" schedules a 600ms debounce Timer; running the tap and the
    // wait on the real loop lets the timer fire and setExerciseWeight complete.
    await tester.runAsync(() async {
      await tester.tap(find.byIcon(Icons.add).first);
      await Future<void>.delayed(const Duration(milliseconds: 800));
    });
    await tester.pump();

    final after = (await tester.runAsync(
      () => StorageService.instance.getExerciseState(name),
    ))!.weight;
    expect(after, before + kWeightIncrement);
  });

  testWidgets('device flow: shows a message when the token cannot be saved', (
    tester,
  ) async {
    // Throwing secure storage makes SyncSettings.save() fail.
    installFakeSecureStorage(throwing: true);
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

      await openAdvanced(tester);
      await tester.ensureVisible(find.text('Connect GitHub'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect GitHub'));
      await _pumpUntil(
        tester,
        () => find
            .textContaining('could not save the token')
            .evaluate()
            .isNotEmpty,
      );
      expect(
        find.textContaining('could not save the token'),
        findsOneWidget,
      );
    });
  });

  testWidgets('device flow: shows a message when verification fails', (
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
      // The post-connect verification GET fails → GitHubSyncError.
      return http.Response('boom', 500);
    });

    await tester.runAsync(() async {
      await tester.pumpWidget(_wrap(httpClient: mock));
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tester.pump();
      await _scrollToGitHubSync(tester);

      await openAdvanced(tester);
      await tester.ensureVisible(find.text('Connect GitHub'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect GitHub'));
      await _pumpUntil(
        tester,
        () => find.textContaining('NOT syncing').evaluate().isNotEmpty,
      );
      expect(find.textContaining('NOT syncing'), findsOneWidget);
    });
  });

  testWidgets('device flow: renders the pending "verifying" status', (
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
      // Hold the verification in-flight so the pending status tile is
      // observable before it resolves to success.
      await Future<void>.delayed(const Duration(milliseconds: 600));
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

      await openAdvanced(tester);
      await tester.ensureVisible(find.text('Connect GitHub'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Connect GitHub'));
      await _pumpUntil(
        tester,
        () => find.textContaining('verifying').evaluate().isNotEmpty,
      );
      // Pending tile (spinner + white70 status colour) is now on screen.
      expect(find.textContaining('verifying'), findsOneWidget);

      await _pumpUntil(
        tester,
        () =>
            find.textContaining('Connected and verified').evaluate().isNotEmpty,
      );
      expect(find.textContaining('Connected and verified'), findsOneWidget);
    });
  });

  testWidgets(
    'a rejected stored token recovers from the backup instead of nagging',
    (tester) async {
      // load() only consults the backup when the keystore is EMPTY, so a
      // stale keystore entry would otherwise shadow a good backup forever
      // and demand a pointless re-authorization.
      final tempDir = Directory.systemTemp.createTempSync('settings_recover_');
      BackupService.baseDirForTesting = tempDir.path;
      addTearDown(() {
        BackupService.baseDirForTesting = kBackupDir;
        tempDir.deleteSync(recursive: true);
      });

      installFakeSecureStorage(initial: {'sync.token': 'stale'});
      // save() writes the external-storage backup: real file I/O, which hangs
      // in the widget-test fake-async zone (same reason _seed uses runAsync).
      await tester.runAsync(
        () async => const SyncSettings(token: 'good').save(),
      );
      installFakeSecureStorage(initial: {'sync.token': 'stale'});

      final mock = MockClient((req) async {
        if (req.headers['Authorization']?.contains('good') != true) {
          return http.Response('Bad credentials', 401);
        }
        return http.Response(
          jsonEncode({'content': base64Encode(utf8.encode('{}')), 'sha': 's'}),
          200,
        );
      });

      await _pump(tester, _wrap(httpClient: mock));
      await _scrollToGitHubSync(tester);

      expect(find.textContaining('recovered the saved token'), findsOneWidget);
      expect(find.textContaining('NOT connected'), findsNothing);
    },
  );
}

/// A real [FirebaseRestClient] that is never called: the settings screen only
/// checks it for null, so no network or keystore is touched.
FirebaseRestClient _stubFirebaseClient() => FirebaseRestClient(
  databaseUrl: 'https://example.invalid',
  auth: FirebaseTokenProvider(apiKey: 'k', store: InMemoryCredentialStore()),
);
