// The run screen's big numbers: moving time, distance, the run's average pace
// and, with a pace target on, the current pace coloured by the band.
part of 'run_screen.dart';

class _Numbers extends StatelessWidget {
  const _Numbers({required this.recorder});

  final RunRecorder recorder;

  /// Green on pace, red off it, plain while there is no verdict yet.
  Color _paceColour(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colors = Theme.of(context).extension<AppStatusColors>()!;
    final band = recorder.coach.band;
    if (band == null) return scheme.onSurface;
    return band == PaceBand.onPace ? colors.success : scheme.error;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    const figures = [FontFeature.tabularFigures()];
    Widget big(Key key, String text, double size, Color color) => FittedBox(
      fit: BoxFit.scaleDown,
      child: Text(
        text,
        key: key,
        style: TextStyle(
          fontSize: size,
          fontWeight: FontWeight.w600,
          color: color,
          fontFeatures: figures,
        ),
      ),
    );
    Widget small(IconData icon, Key key, String text, {Color? colour}) =>
        Expanded(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: scheme.onSurfaceVariant),
              const SizedBox(width: AppSpacing.xs),
              Flexible(child: big(key, text, 48, colour ?? scheme.onSurface)),
            ],
          ),
        );
    final current = recorder.coach.pace;
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Flexible(
          child: big(
            const Key('run_time'),
            formatDuration(recorder.seconds),
            96,
            scheme.onSurface,
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            small(
              Icons.straighten,
              const Key('run_distance'),
              formatDistanceKm(recorder.distanceM),
            ),
            small(
              Icons.speed,
              const Key('run_pace'),
              formatPace(
                seconds: recorder.seconds,
                distanceM: recorder.distanceM,
              ),
            ),
            if (recorder.coach.target != null)
              small(
                Icons.bolt,
                const Key('run_pace_now'),
                current == null ? '-:--' : formatPaceSeconds(current.round()),
                colour: _paceColour(context),
              ),
          ],
        ),
      ],
    );
  }
}
