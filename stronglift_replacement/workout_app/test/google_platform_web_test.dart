import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/google_platform_web.dart';

void main() {
  test('the web half always reports the programmatic flow unsupported', () {
    // The conditional export in google_platform.dart never pulls this file
    // in on the Linux test host (it resolves to google_platform_io.dart
    // instead), so it would otherwise never appear in coverage at all.
    // Imported directly here for that reason, same pattern as
    // sync_state_factory_web_test.dart elsewhere in this app family.
    expect(googleSignInSupported, isFalse);
  });
}
