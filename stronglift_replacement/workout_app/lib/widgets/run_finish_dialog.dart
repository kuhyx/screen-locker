/// The confirm step before a run ends: a red check ends it, a cross goes back.
/// No words (textgate): colour and two icons carry the whole question.
library;

import 'package:material_ui/material_ui.dart';
import 'package:workout_app/ui/theme.dart';

/// Asks whether to end the run. True only for the red check; the cross, the
/// back button and a tap outside all answer false, so nothing but a deliberate
/// check ends a run.
Future<bool> showRunFinishDialog(BuildContext context) async {
  final end = await showDialog<bool>(
    context: context,
    builder: (context) {
      final scheme = Theme.of(context).colorScheme;
      Widget choice(String id, IconData icon, Color fill, bool answer) =>
          IconButton.filled(
            key: Key('run_finish_$id'),
            onPressed: () => Navigator.of(context).pop(answer),
            iconSize: 48,
            style: IconButton.styleFrom(
              fixedSize: const Size.square(96),
              backgroundColor: fill,
              foregroundColor: scheme.onPrimary,
            ),
            icon: Icon(icon, semanticLabel: id),
          );
      return Dialog(
        key: const Key('run_finish_dialog'),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              choice('confirm', Icons.check, scheme.error, true),
              choice(
                'cancel',
                Icons.close,
                scheme.surfaceContainerHighest,
                false,
              ),
            ],
          ),
        ),
      );
    },
  );
  return end ?? false;
}
