/// The optional pace target before a run: a flag icon that switches it on,
/// and then `- m:ss +` in [kPaceStep] steps (holding a button repeats).
///
/// Icons and digits only (textgate). Deliberately not a wheel: a wheel is a
/// `Scrollable`, and the run screen must have nothing that scrolls (R7).
library;

import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:workout_app/services/pace_band.dart';
import 'package:workout_app/services/run_format.dart';
import 'package:workout_app/ui/theme.dart';

/// How often a held step button repeats once it has started.
const Duration kPaceRepeatEvery = Duration(milliseconds: 120);

/// The pace-target control shown beside the start button.
class RunPacePicker extends StatelessWidget {
  /// Creates the control; [seconds] is the target in seconds per kilometre.
  const RunPacePicker({
    required this.on,
    required this.seconds,
    required this.onToggle,
    required this.onChanged,
    super.key,
  });

  /// Whether a target is set.
  final bool on;

  /// The target while [on].
  final int seconds;

  /// Called when the flag is tapped.
  final VoidCallback onToggle;

  /// Called with the new target for each step.
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          key: const Key('run_pace_toggle'),
          onPressed: onToggle,
          color: on ? scheme.primary : scheme.onSurfaceVariant,
          icon: Icon(
            on ? Icons.flag : Icons.flag_outlined,
            semanticLabel: 'pace target',
          ),
        ),
        if (on) ...[
          _StepButton(
            id: 'run_pace_minus',
            icon: Icons.remove,
            onStep: seconds > kMinPaceTarget
                ? () => onChanged(seconds - kPaceStep)
                : null,
          ),
          Flexible(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
              // Scales down rather than overflow at large system text sizes.
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  formatPaceSeconds(seconds),
                  key: const Key('run_pace_value'),
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w600,
                    fontFeatures: [FontFeature.tabularFigures()],
                  ),
                ),
              ),
            ),
          ),
          _StepButton(
            id: 'run_pace_plus',
            icon: Icons.add,
            onStep: seconds < kMaxPaceTarget
                ? () => onChanged(seconds + kPaceStep)
                : null,
          ),
        ],
      ],
    );
  }
}

/// A step button: a tap steps once, holding steps on repeat. Null [onStep]
/// disables it (the end of the range), which also ends a hold.
class _StepButton extends StatefulWidget {
  const _StepButton({required this.id, required this.icon, this.onStep});

  final String id;
  final IconData icon;
  final VoidCallback? onStep;

  @override
  State<_StepButton> createState() => _StepButtonState();
}

class _StepButtonState extends State<_StepButton> {
  Timer? _timer;
  bool _held = false;

  void _down() {
    _held = false;
    _timer = Timer(kLongPressTimeout, _startRepeating);
  }

  void _startRepeating() {
    _held = true;
    _step();
    _timer = Timer.periodic(kPaceRepeatEvery, (_) => _step());
  }

  void _step() {
    final onStep = widget.onStep;
    if (onStep == null) return _release();
    onStep();
  }

  void _release() {
    _timer?.cancel();
    _timer = null;
  }

  void _tap() {
    // The release of a hold is not one more tap.
    if (_held) {
      _held = false;
      return;
    }
    widget.onStep?.call();
  }

  @override
  void dispose() {
    _release();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Listener(
    onPointerDown: (_) => _down(),
    onPointerUp: (_) => _release(),
    onPointerCancel: (_) => _release(),
    child: IconButton(
      key: Key(widget.id),
      onPressed: widget.onStep == null ? null : _tap,
      icon: Icon(widget.icon, semanticLabel: widget.id),
    ),
  );
}
