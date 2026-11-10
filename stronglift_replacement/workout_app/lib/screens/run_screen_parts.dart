// The run screen's bands: status icons and the buttons (the numbers have
// their own part).
part of 'run_screen.dart';

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

/// The red problem icon; [size] 24 in the status row, large when it is the
/// only thing on the screen (location refused).
class _IssueButton extends StatelessWidget {
  const _IssueButton({
    required this.issue,
    required this.onTap,
    required this.size,
  });

  final RunIssue issue;
  final VoidCallback? onTap;
  final double size;

  @override
  Widget build(BuildContext context) {
    final face = _issueFace(issue);
    if (face == null) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    final colors = Theme.of(context).extension<AppStatusColors>()!;
    return IconButton(
      key: Key('run_issue_${issue.name}'),
      onPressed: onTap,
      iconSize: size,
      icon: Icon(
        face.icon,
        color: face.danger ? scheme.error : colors.warning,
        semanticLabel: issue.name,
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  const _StatusRow({
    required this.controller,
    required this.uploader,
    required this.issue,
  });

  final RunController controller;
  final RunUploader uploader;

  /// The problem icon, or null when it is shown elsewhere (or not at all).
  final Widget? issue;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colors = Theme.of(context).extension<AppStatusColors>()!;
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
          ?issue,
        ],
      ),
    );
  }
}

class _Controls extends StatelessWidget {
  const _Controls({
    required this.controller,
    required this.starting,
    required this.paceOn,
    required this.paceTarget,
    required this.onPaceToggle,
    required this.onPaceChanged,
    required this.onStart,
    required this.onAgain,
    required this.onClose,
  });

  final RunController controller;
  final bool starting;
  final bool paceOn;
  final int paceTarget;
  final VoidCallback onPaceToggle;
  final ValueChanged<int> onPaceChanged;
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
        Flexible(
          child: RunPacePicker(
            on: paceOn,
            seconds: paceTarget,
            onToggle: onPaceToggle,
            onChanged: onPaceChanged,
          ),
        ),
        button(
          'start',
          Icons.play_arrow,
          starting || !controller.canStart ? null : onStart,
        ),
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
