/// The upload queue as an icon (and, while runs wait, a count).
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:workout_app/services/run_uploader.dart';
import 'package:workout_app/ui/theme.dart';

/// The icon for a queue state; shared by the badge and its tests.
IconData uploadBadgeIcon(UploadHealth health) => switch (health) {
  UploadHealth.idle => Icons.cloud_done,
  UploadHealth.uploading => Icons.cloud_upload,
  UploadHealth.retrying => Icons.cloud_off,
  UploadHealth.notConfigured => Icons.link_off,
  UploadHealth.sandbox => Icons.cloud_queue,
};

/// Shows [uploader]'s state; a tap runs the queue again right now.
class RunUploadBadge extends StatelessWidget {
  /// Creates a badge over [uploader].
  const RunUploadBadge({required this.uploader, super.key});

  /// The queue shown.
  final RunUploader uploader;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final status = Theme.of(context).extension<AppStatusColors>()!;
    return ValueListenableBuilder<RunUploadStatus>(
      valueListenable: uploader.status,
      builder: (context, s, _) {
        final color = switch (s.health) {
          UploadHealth.idle => status.success,
          UploadHealth.uploading => scheme.primary,
          UploadHealth.retrying => status.warning,
          UploadHealth.notConfigured => scheme.error,
          UploadHealth.sandbox => scheme.onSurfaceVariant,
        };
        return InkResponse(
          key: const Key('run_upload_badge'),
          onTap: () => unawaited(uploader.uploadPending()),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.sm),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  uploadBadgeIcon(s.health),
                  color: color,
                  semanticLabel: s.health.name,
                ),
                if (s.pending > 0) ...[
                  const SizedBox(width: AppSpacing.xs),
                  Text(
                    '${s.pending}',
                    key: const Key('run_upload_pending'),
                    style: TextStyle(color: color, fontSize: AppTextSize.body),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}
