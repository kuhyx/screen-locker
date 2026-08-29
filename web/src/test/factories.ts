import type {
  DecisionsPayload,
  HealthPayload,
  StatusPayload,
} from '../types'

export function makeStatus(over: Partial<StatusPayload> = {}): StatusPayload {
  return {
    snapshot: {
      today: {
        date: '2026-08-29',
        label: 'Sat Aug 29',
        entry_types: [],
        source: '',
        counted: false,
        day_count: 0,
        is_sick_day: false,
      },
      week: {
        days: [],
        counted_count: 3,
        minimum: 5,
        remaining: 2,
        extra: 0,
      },
      lock_explanation: {
        fired: false,
        stage: 'scheduled_skip',
        reason: 'Manually scheduled skip day.',
        trace: [],
        heat_skip_evaluated: false,
        sources_degraded: false,
      },
      generated_at: '2026-08-29T20:30:00+00:00',
    },
    summary_line: '… 3/5 workouts',
    compliance_state: 'warn',
    gaming: {
      workout_today: false,
      credits_today: 0,
      reason: 'no counted workout logged today',
    },
    ...over,
  }
}

export function makeHealth(over: Partial<HealthPayload> = {}): HealthPayload {
  return {
    timers_checked: true,
    timers: [
      {
        name: 'workout-locker.timer',
        enabled: true,
        scheduled: true,
        armed: true,
        describe: 'OK       workout-locker.timer: enabled and scheduled',
      },
    ],
    armed: true,
    disarmed: false,
    disarm_marker: '/home/kuhy/.local/share/screen_locker/DISARMED',
    log_file: '/home/kuhy/screen-locker/screen_locker/log.json',
    log_age_seconds: 3600,
    decision_log_file: '/home/kuhy/.local/share/screen_locker/decisions.jsonl',
    last_decision_age_seconds: 120,
    ...over,
  }
}

export function makeDecisions(
  over: Partial<DecisionsPayload> = {},
): DecisionsPayload {
  return {
    total: 3000,
    returned: 1,
    decisions: [
      {
        timestamp: '2026-08-29T20:01:02+00:00',
        locked: false,
        reason: 'weekly_minimum_met',
        weekly_count: 5,
        weekly_required: 5,
        also: 'early_bird_window_active',
      },
    ],
    ...over,
  }
}
