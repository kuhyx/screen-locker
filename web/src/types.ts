/** Shapes served by screen_locker._web_payload. */

/** One predicate the lock decision walked past, and whether it fired. */
export interface TraceStep {
  readonly name: string
  readonly fired: boolean
  readonly reason: string
}

/** Why the locker would or would not fire right now. */
export interface LockExplanation {
  readonly fired: boolean
  readonly stage: string
  readonly reason: string
  readonly trace: readonly TraceStep[]
  readonly heat_skip_evaluated: boolean
  readonly sources_degraded: boolean
}

/** One day of this ISO week. */
export interface DayStatus {
  readonly date: string
  readonly label: string
  readonly entry_types: readonly string[]
  readonly source: string
  readonly counted: boolean
  readonly day_count: number
  readonly is_sick_day: boolean
}

/** This ISO week against the weekly minimum. */
export interface WeeklySummary {
  readonly days: readonly DayStatus[]
  readonly counted_count: number
  readonly minimum: number
  readonly remaining: number
  readonly extra: number
}

/** The parts of the status snapshot this UI renders. */
export interface StatusSnapshot {
  readonly today: DayStatus
  readonly week: WeeklySummary
  readonly lock_explanation: LockExplanation
  readonly generated_at: string
}

/** The fact the gaming budget turns on. */
export interface GamingFact {
  readonly workout_today: boolean
  readonly credits_today: number
  readonly reason: string
}

/** GET /api/status. */
/** A locker run that has decided to lock but is waiting for the screen. */
export interface QueueWait {
  readonly blocked_by: readonly string[]
  readonly elapsed_seconds: number
  readonly updated: string
}

export interface StatusPayload {
  readonly snapshot: StatusSnapshot
  readonly summary_line: string
  readonly compliance_state: string
  readonly gaming: GamingFact
  /** Non-null while a run is queued behind a higher-ranked screen holder. */
  readonly queue_wait: QueueWait | null
  /** Whether workout-locker.service is running; null means "could not ask". */
  readonly locker_running: boolean | null
}

/** One recorded decision from decisions.jsonl. */
export interface Decision {
  readonly timestamp: string
  readonly locked: boolean | null
  readonly reason: string
  readonly detail?: string
  readonly weekly_count?: number
  readonly weekly_required?: number
  readonly also?: string
  readonly mode?: string
  /** Set when consecutive identical decisions were folded into one row. */
  readonly repeat_count?: number
  /** The most recent sighting of a collapsed row; `timestamp` is the first. */
  readonly last_timestamp?: string
  /** Server-rendered local time. Preferred over formatting `timestamp` here:
   *  LibreWolf's resistFingerprinting pins the browser's Date to UTC. */
  readonly local_time?: string
  readonly local_last_time?: string
}

/** GET /api/decisions. */
export interface DecisionsPayload {
  readonly total: number
  readonly returned: number
  readonly decisions: readonly Decision[]
}

/** One systemd timer's arming state. */
export interface TimerHealth {
  readonly name: string
  readonly enabled: boolean
  readonly scheduled: boolean
  readonly armed: boolean
  readonly describe: string
}

/** GET /api/health. */
export interface HealthPayload {
  readonly timers_checked: boolean
  readonly timers: readonly TimerHealth[]
  readonly armed: boolean
  readonly disarmed: boolean
  readonly disarm_marker: string
  readonly log_file: string
  readonly log_age_seconds: number | null
  readonly decision_log_file: string
  readonly last_decision_age_seconds: number | null
}
