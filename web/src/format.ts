/** Pure formatting helpers, shared by the three views. */

const MINUTE = 60
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/**
 * Render a duration in seconds as a short human age ("3m", "5h", "2d").
 *
 * Returns "unknown" for null so a missing timestamp can never be mistaken for
 * a fresh one — the whole point of the Health view is that silence is visible.
 */
export function formatAge(seconds: number | null): string {
  if (seconds === null) return 'unknown'
  if (seconds < 0) return 'in the future'
  if (seconds < MINUTE) return `${String(Math.floor(seconds))}s`
  if (seconds < HOUR) return `${String(Math.floor(seconds / MINUTE))}m`
  if (seconds < DAY) return `${String(Math.floor(seconds / HOUR))}h`
  return `${String(Math.floor(seconds / DAY))}d`
}

/** Render an ISO-8601 timestamp as a local "MMM DD HH:MM" stamp. */
export function formatStamp(iso: string): string {
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return iso
  return when.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Turn a decision reason slug into a sentence.
 *
 * Falls back to the slug with underscores stripped, so a reason added to the
 * Python side later still reads sensibly here instead of rendering blank.
 */
export function describeReason(reason: string): string {
  const known: Record<string, string> = {
    enforced: 'Locked — no skip condition applied',
    weekly_minimum_met: 'Skipped — weekly minimum already met',
    scheduled_skip_day: 'Skipped — this date was scheduled off',
    relaxed_day: 'Relaxed day (Tue–Thu) — lock optional',
    relaxed_day_already_skipped: 'Skipped — relaxed day already dismissed',
    workout_logged_today: 'Skipped — a workout was logged today',
    early_bird_window_active: 'Skipped — inside the early-bird window',
    early_bird_banked: 'Skipped — early-bird marker banked',
    early_bird_auto_upgraded: 'Skipped — early-bird workout confirmed',
    sick_day: 'Skipped — sick day',
    sick_day_auto_upgraded: 'Skipped — sick day, workout confirmed',
    wake_alarm_skip: 'Skipped — earned by the wake alarm',
    heat_skip: 'Skipped — too hot',
    no_sick_day_to_verify: 'Nothing to verify',
    mode_makes_no_decision: 'No decision (status or sync-only run)',
  }
  return known[reason] ?? reason.replace(/_/g, ' ')
}

/** Budget hours the enforcer will apply, given whether today has a workout. */
export function budgetHours(workoutToday: boolean): number {
  return workoutToday ? 8 : 6
}
