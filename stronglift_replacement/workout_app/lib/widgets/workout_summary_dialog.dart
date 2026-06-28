/// Dialog shown after a workout is finished, summarising results.
library;

import 'package:flutter/material.dart';
import 'package:workout_app/models/workout_session.dart';
import 'package:workout_app/services/sync_service.dart';

/// Dialog that summarises a completed workout and reports the sync status.
class WorkoutSummaryDialog extends StatelessWidget {
  /// Creates a [WorkoutSummaryDialog].
  const WorkoutSummaryDialog({
    required this.session,
    required this.syncResult,
    super.key,
  });

  /// The completed workout session to summarise.
  final WorkoutSession session;

  /// Result of writing the session to disk/HTTP server.
  final SyncResult syncResult;

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '${d.inHours > 0 ? '${d.inHours}h ' : ''}${m}m ${s}s';
  }

  @override
  Widget build(BuildContext context) {
    final succeeded = session.fullySucceeded;
    return AlertDialog(
      backgroundColor: Colors.grey.shade900,
      title: Text(
        succeeded ? 'Workout Complete! 💪' : 'Workout Done',
        style: TextStyle(
          color: succeeded ? Colors.greenAccent : Colors.orangeAccent,
          fontWeight: FontWeight.bold,
        ),
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Duration: ${_fmt(session.duration)}',
            style: const TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 8),
          ...session.exercises.map(
            (e) => Text(
              '${e.exercise.name}: ${e.succeeded ? "✓" : "✗"}',
              style: TextStyle(
                color: e.succeeded ? Colors.greenAccent : Colors.redAccent,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            syncResult.success
                ? 'Saved to ${syncResult.path}'
                : 'Sync failed: ${syncResult.error}',
            style: TextStyle(
              color: syncResult.success ? Colors.white54 : Colors.redAccent,
              fontSize: 12,
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.of(context).popUntil((r) => r.isFirst);
          },
          child: const Text(
            'Back to Home',
            style: TextStyle(color: Colors.white),
          ),
        ),
      ],
    );
  }
}
