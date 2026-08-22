// The flag the Linux runner and the Dart side must agree on.
//
// They read the same argument on purpose: if the runner grabbed the screen
// while Dart still showed its exits, the lock would be dismissible.
import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/lock_mode.dart';

void main() {
  group('parseLockMode', () {
    test('is false for an ordinary windowed launch', () {
      expect(parseLockMode([]), isFalse);
    });

    test('is true when the runner was given the flag', () {
      expect(parseLockMode([kLockModeFlag]), isTrue);
    });

    test('finds the flag alongside the other arguments', () {
      expect(parseLockMode(['--demo-escape', kLockModeFlag]), isTrue);
    });

    test('does not match a different flag', () {
      expect(parseLockMode(['--demo-escape']), isFalse);
    });
  });

  test('lockModeEnabled defaults to false, so tests behave as before', () {
    expect(lockModeEnabled, isFalse);
  });
}
