import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:workout_app/services/desktop_config_dir.dart';
import 'package:workout_app/services/firebase_backend.dart';

/// Runs [body] with the suite-wide override cleared, restoring it after.
void _withoutOverride(void Function() body) {
  final saved = desktopConfigRootOverride;
  desktopConfigRootOverride = null;
  try {
    body();
  } finally {
    desktopConfigRootOverride = saved;
  }
}

void main() {
  const home = '/home/someone';
  const testEnv = {'HOME': home, 'FLUTTER_TEST': 'true'};

  group('suite isolation', () {
    test('flutter test exports FLUTTER_TEST, which the guard keys on', () {
      expect(Platform.environment.containsKey('FLUTTER_TEST'), isTrue);
    });

    test('flutter_test_config points every test at a temp root', () {
      final root = desktopConfigRoot();
      expect(root, isNotNull);
      expect(root, desktopConfigRootOverride);
      expect(p.isWithin(Directory.systemTemp.path, root!), isTrue);
      final realHome = Platform.environment['HOME'];
      if (realHome != null && realHome.isNotEmpty) {
        expect(p.isWithin(realHome, root), isFalse);
      }
    });

    test('a stored session lands in the temp root, not ~/.config', () async {
      // The write the 2026-09 incident performed: a sign-in test stored its
      // fixture refresh token through credentialStore() on the Linux host.
      await credentialStore().write('firebase.credentials', '{}');
      final written = File(
        p.join(
          desktopConfigRootOverride!,
          'screen_locker',
          'firebase_auth.json',
        ),
      );
      expect(written.existsSync(), isTrue);
    });

    test('without the override, storing a session fails loudly', () async {
      final saved = desktopConfigRootOverride;
      desktopConfigRootOverride = null;
      addTearDown(() => desktopConfigRootOverride = saved);
      await expectLater(
        credentialStore().write('firebase.credentials', '{}'),
        throwsStateError,
      );
    });
  });

  group('desktopConfigRoot', () {
    test('is HOME/.config outside flutter test', () {
      _withoutOverride(() {
        expect(
          desktopConfigRoot(environment: const {'HOME': home}),
          '$home/.config',
        );
      });
    });

    test('is null when HOME is unset or empty', () {
      _withoutOverride(() {
        expect(desktopConfigRoot(environment: const {}), isNull);
        expect(desktopConfigRoot(environment: const {'HOME': ''}), isNull);
        expect(
          desktopConfigRoot(environment: const {'FLUTTER_TEST': 'true'}),
          isNull,
        );
      });
    });

    test('refuses the real ~/.config under flutter test', () {
      _withoutOverride(() {
        expect(
          () => desktopConfigRoot(environment: testEnv),
          throwsA(
            isA<StateError>().having(
              (e) => e.message,
              'message',
              contains('desktopConfigRootOverride'),
            ),
          ),
        );
      });
    });

    test('refuses an override inside the real ~/.config too', () {
      final saved = desktopConfigRootOverride;
      addTearDown(() => desktopConfigRootOverride = saved);
      desktopConfigRootOverride = '$home/.config/elsewhere';
      expect(() => desktopConfigRoot(environment: testEnv), throwsStateError);
    });

    test('returns an override outside the real ~/.config', () {
      final saved = desktopConfigRootOverride;
      addTearDown(() => desktopConfigRootOverride = saved);
      desktopConfigRootOverride = '/tmp/isolated';
      expect(desktopConfigRoot(environment: testEnv), '/tmp/isolated');
      expect(
        desktopConfigRoot(environment: const {'HOME': home}),
        '/tmp/isolated',
      );
    });
  });
}
