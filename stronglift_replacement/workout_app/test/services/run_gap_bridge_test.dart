import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_gap_bridge.dart';

void main() {
  group('bridgeCredits (2:30 to 12:00 min/km)', () {
    test('a steady 5:00/km jog across a gap is credited', () {
      expect(bridgeCredits(stepM: 1000, gapSeconds: 300), isTrue);
    });

    test('the pace bounds are inclusive', () {
      expect(bridgeCredits(stepM: 1000, gapSeconds: 150), isTrue); // 2:30
      expect(bridgeCredits(stepM: 1000, gapSeconds: 720), isTrue); // 12:00
    });

    test('faster than 2:30/km is a vehicle: drawn, not credited', () {
      expect(bridgeCredits(stepM: 1000, gapSeconds: 149), isFalse);
    });

    test('slower than 12:00/km is standing about: not credited', () {
      expect(bridgeCredits(stepM: 1000, gapSeconds: 721), isFalse);
    });

    test('no movement or no time credits nothing', () {
      expect(bridgeCredits(stepM: 0, gapSeconds: 600), isFalse);
      expect(bridgeCredits(stepM: 100, gapSeconds: 0), isFalse);
      expect(bridgeCredits(stepM: -1, gapSeconds: 60), isFalse);
    });

    test('the minimum speed constant matches the slowest pace', () {
      expect(kBridgeMinSpeedMps, closeTo(1000 / 720, 1e-9));
    });
  });
}
