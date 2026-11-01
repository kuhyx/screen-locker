/// A whole number that counts to its true value instead of snapping to it.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/ui/theme.dart';

/// Rebuilds [builder] with a number that eases from 0 to [value] on arrival,
/// and from the number on screen to a new [value] when it changes.
///
/// The animation only travels towards the real value and always ends on it;
/// nothing here can show a number the data does not hold. With the OS
/// animations setting off, the duration collapses and the real value shows at
/// once.
class AnimatedCounter extends StatelessWidget {
  /// Creates an [AnimatedCounter].
  const AnimatedCounter({
    required this.value,
    required this.builder,
    super.key,
  });

  /// The true value to arrive at.
  final int value;

  /// Draws the number currently on its way to [value].
  final Widget Function(int shown) builder;

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<int>(
    tween: IntTween(begin: 0, end: value),
    duration: motionDuration(context, AppDuration.slow),
    curve: AppCurve.decelerate,
    builder: (_, shown, _) => builder(shown),
  );
}
