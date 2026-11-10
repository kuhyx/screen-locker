// The run screen's three bands: status icons, the big numbers, the buttons.
part of 'run_screen.dart';

IconData _sportIcon(RunSport sport) => switch (sport) {
  RunSport.running => Icons.directions_run,
  RunSport.walking => Icons.directions_walk,
};

/// Problems with the recording, as an icon (null when there is none).
({IconData icon, bool danger})? _issueFace(RunIssue issue) => switch (issue) {
  RunIssue.none => null,
  RunIssue.denied ||
  RunIssue.deniedForever ||
  RunIssue.serviceOff => (icon: Icons.location_disabled, danger: true),
  RunIssue.mockedLocation => (icon: Icons.wrong_location, danger: true),
  RunIssue.streamError => (icon: Icons.gps_off, danger: false),
  RunIssue.tooShort => (icon: Icons.error_outline, danger: true),
};

class _StatusRow extends StatelessWidget {
  const _StatusRow({
    required this.controller,
    required this.uploader,
    required this.openSettings,
  });

  final RunController controller;
  final RunUploader uploader;
  final Future<bool> Function() openSettings;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colors = Theme.of(context).extension<AppStatusColors>()!;
    final recorder = controller.recorder;
    final issue = _issueFace(recorder.issue);
    final fixable =
        recorder.issue == RunIssue.deniedForever ||
        recorder.issue == RunIssue.serviceOff;
    final serviceIcon = switch (controller.serviceState) {
      RunServiceState.runningHidden => (Icons.notifications_off, false),
      RunServiceState.failed => (Icons.warning_amber, true),
      _ => null,
    };
    final saved = controller.saved;
    return SizedBox(
      height: 48,
      child: Row(
        children: [
          RunUploadBadge(uploader: uploader),
          const Spacer(),
          if (controller.saving)
            const SizedBox.square(
              dimension: 24,
              child: CircularProgressIndicator(
                key: Key('run_saving'),
                strokeWidth: 2,
              ),
            ),
          if (saved != null)
            Icon(
              saved.stored ? Icons.check_circle : Icons.error,
              key: Key(saved.stored ? 'run_saved_ok' : 'run_saved_failed'),
              color: saved.stored ? colors.success : scheme.error,
              semanticLabel: saved.stored ? 'saved' : 'not saved',
            ),
          if (serviceIcon != null)
            Padding(
              padding: const EdgeInsets.only(left: AppSpacing.sm),
              child: Icon(
                serviceIcon.$1,
                key: const Key('run_service_issue'),
                color: serviceIcon.$2 ? scheme.error : colors.warning,
                semanticLabel: controller.serviceState.name,
              ),
            ),
          if (issue != null)
            IconButton(
              key: Key('run_issue_${recorder.issue.name}'),
              onPressed: fixable ? () => unawaited(openSettings()) : null,
              icon: Icon(
                issue.icon,
                color: issue.danger ? scheme.error : colors.warning,
                semanticLabel: recorder.issue.name,
              ),
            ),
          Padding(
            padding: const EdgeInsets.only(left: AppSpacing.sm),
            child: Icon(
              _sportIcon(recorder.sport),
              color: scheme.onSurfaceVariant,
              semanticLabel: recorder.sport.name,
            ),
          ),
        ],
      ),
    );
  }
}

class _Numbers extends StatelessWidget {
  const _Numbers({required this.recorder});

  final RunRecorder recorder;

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
    Widget small(IconData icon, Key key, String text) => Expanded(
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: scheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.sm),
          Flexible(child: big(key, text, 48, scheme.onSurface)),
        ],
      ),
    );
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
          ],
        ),
      ],
    );
  }
}

class _Controls extends StatelessWidget {
  const _Controls({
    required this.controller,
    required this.starting,
    required this.onStart,
    required this.onAgain,
    required this.onClose,
  });

  final RunController controller;
  final bool starting;
  final VoidCallback onStart;
  final VoidCallback onAgain;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final recorder = controller.recorder;
    final scheme = Theme.of(context).colorScheme;
    Widget button(
      String id,
      IconData icon,
      VoidCallback? onTap, {
      Color? tint,
    }) {
      return IconButton.filled(
        key: Key('run_$id'),
        onPressed: onTap,
        iconSize: 40,
        style: IconButton.styleFrom(
          fixedSize: const Size.square(88),
          backgroundColor: tint ?? scheme.primary,
          foregroundColor: scheme.onPrimary,
        ),
        icon: Icon(icon, semanticLabel: id),
      );
    }

    final buttons = switch (recorder.phase) {
      RunPhase.idle => [
        SegmentedButton<RunSport>(
          key: const Key('run_sport'),
          showSelectedIcon: false,
          segments: [
            for (final sport in RunSport.values)
              ButtonSegment(
                value: sport,
                icon: Icon(_sportIcon(sport), semanticLabel: sport.name),
              ),
          ],
          selected: {recorder.sport},
          onSelectionChanged: (s) => recorder.selectSport(s.single),
        ),
        button('start', Icons.play_arrow, starting ? null : onStart),
      ],
      RunPhase.recording => [
        button('pause', Icons.pause, controller.pause),
        button(
          'finish',
          Icons.stop,
          () => unawaited(controller.finish()),
          tint: scheme.error,
        ),
      ],
      RunPhase.paused => [
        button('resume', Icons.play_arrow, controller.resume),
        button(
          'finish',
          Icons.stop,
          () => unawaited(controller.finish()),
          tint: scheme.error,
        ),
      ],
      RunPhase.finished => [
        button('again', Icons.refresh, controller.saving ? null : onAgain),
        button('close', Icons.check, controller.saving ? null : onClose),
      ],
    };
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: buttons,
    );
  }
}
