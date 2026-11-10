import 'package:flutter_test/flutter_test.dart';
import 'package:workout_app/services/run_notification.dart';

void main() {
  test('the notification is distance, then time and pace, digits only', () {
    final copy = runNotificationCopy(metres: 3524, movingSeconds: 723);
    expect(copy.title, '3.52');
    expect(copy.body, '12:03  3:25');
  });

  test('before a pace exists the body shows a dash', () {
    final copy = runNotificationCopy(metres: 0, movingSeconds: 0);
    expect(copy.title, '0.00');
    expect(copy.body, '0:00  -:--');
  });

  test('a pace target adds the current pace, to the nearest 5 s', () {
    final copy = runNotificationCopy(
      metres: 3524,
      movingSeconds: 723,
      currentPace: 333.3,
    );
    expect(copy.body, '12:03  3:25  5:35');
    expect(
      runNotificationCopy(metres: 1, movingSeconds: 1, currentPace: 332.4).body,
      endsWith('5:30'),
    );
  });
}
