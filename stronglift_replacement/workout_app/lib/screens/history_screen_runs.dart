// The runs overview on HistoryScreen: one fixed-height strip of compact
// tiles (newest first, swipe sideways for older ones) so it costs no
// vertical space (R7). No words: icons and numbers only.
//
// See history_screen_charts.dart for why these are `part` files.
part of 'history_screen.dart';

/// Pieces of the State kept here so history_screen.dart stays under the line
/// cap: the month-paged calendar and opening a run's detail.
extension _RunsAndCalendar on _HistoryScreenState {
  Widget _calendar(Set<String> dates) => WorkoutCalendar(
    workoutDates: dates,
    month: _calendarMonth,
    onPrevMonth: () => _shiftMonth(-1),
    onNextMonth: () => _shiftMonth(1),
  );

  Future<void> _openRun(RunRecord record) async {
    final full = await StorageService.instance.getRun(record.track.id);
    if (full == null || !mounted) return;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => RunDetailScreen(
          track: full.track,
          tileProviderOpener: widget.tileProviderOpener,
        ),
      ),
    );
  }
}

class _RunsStrip extends StatelessWidget {
  const _RunsStrip({required this.runs, required this.onOpen});

  final List<RunRecord> runs;
  final void Function(RunRecord) onOpen;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      key: const Key('runs_strip'),
      height: 92,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: runs.length,
        separatorBuilder: (_, _) => const SizedBox(width: AppSpacing.sm),
        itemBuilder: (_, i) => _RunTile(
          run: runs[i].track,
          scheme: scheme,
          onTap: () => onOpen(runs[i]),
        ),
      ),
    );
  }
}

class _RunTile extends StatelessWidget {
  const _RunTile({
    required this.run,
    required this.scheme,
    required this.onTap,
  });

  final RunTrack run;
  final ColorScheme scheme;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isRun = run.sport == RunSport.running;
    final value = TextStyle(
      color: scheme.onSurface,
      fontWeight: FontWeight.bold,
      fontSize: AppTextSize.label,
    );
    return Semantics(
      button: true,
      label: isRun ? 'Run' : 'Walk',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        child: Container(
          width: 104,
          padding: const EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHigh,
            borderRadius: BorderRadius.circular(AppRadius.sm),
            border: Border.all(color: scheme.outline),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(
                    isRun ? Icons.directions_run : Icons.directions_walk,
                    size: 18,
                    color: scheme.primary,
                  ),
                  const Spacer(),
                  Text(
                    formatRunDay(run.startedAt),
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: AppTextSize.caption,
                    ),
                  ),
                ],
              ),
              Text(formatDistanceKm(run.distanceM), style: value),
              Text(
                formatDuration(run.totalSeconds),
                style: TextStyle(
                  color: scheme.onSurfaceVariant,
                  fontSize: AppTextSize.caption,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
