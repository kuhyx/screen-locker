// The finish button's pulse: the one cue that finishing is suggested.
part of 'run_screen.dart';

/// Pulses [child] while [pulsing]: the one cue the screen gives that finishing
/// is suggested. A symbol of motion, no words.
class _PulsingFinish extends StatefulWidget {
  const _PulsingFinish({required this.pulsing, required this.child});

  final bool pulsing;
  final Widget child;

  @override
  State<_PulsingFinish> createState() => _PulsingFinishState();
}

class _PulsingFinishState extends State<_PulsingFinish>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 700),
    lowerBound: 0.88,
  );

  @override
  void initState() {
    super.initState();
    _sync();
  }

  @override
  void didUpdateWidget(_PulsingFinish old) {
    super.didUpdateWidget(old);
    _sync();
  }

  void _sync() {
    if (widget.pulsing && !_pulse.isAnimating) {
      _pulse.repeat(reverse: true);
    } else if (!widget.pulsing && _pulse.isAnimating) {
      _pulse.value = 1;
      _pulse.stop();
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ScaleTransition(
    key: Key(widget.pulsing ? 'run_finish_pulse' : 'run_finish_still'),
    scale: widget.pulsing ? _pulse : const AlwaysStoppedAnimation(1),
    child: widget.child,
  );
}
