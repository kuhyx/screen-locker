import { budgetHours } from '../format'
import type { StatusPayload } from '../types'

interface Props {
  readonly status: StatusPayload
}

/** The decision as it stands right now, in words rather than slugs. */
export function NowCard({ status }: Props) {
  const { snapshot, gaming, compliance_state: state } = status
  const { week, lock_explanation: lock } = snapshot
  const hours = budgetHours(gaming.workout_today)

  return (
    <section className="card" aria-labelledby="now-heading">
      <h2 id="now-heading">Now</h2>
      <p className={`headline state-${state}`}>
        {lock.fired ? 'Lock would fire' : 'No lock'}
      </p>
      <p className="muted">{lock.reason}</p>

      <div className="row">
        <span>This week</span>
        <span>
          {week.counted_count}/{week.minimum} workouts
          {week.remaining > 0 ? ` — ${String(week.remaining)} to go` : ''}
        </span>
      </div>
      <div className="row">
        <span>Today</span>
        <span>{gaming.reason}</span>
      </div>
      <div className="row">
        <span>Gaming budget today</span>
        <span>
          <span className={gaming.workout_today ? 'pill pill-ok' : 'pill pill-lock'}>
            {hours}h
          </span>{' '}
          <span className="muted">
            {gaming.workout_today
              ? 'earned by a workout logged today'
              : 'cut from 8h — no workout logged today'}
          </span>
        </span>
      </div>
      <div className="row">
        <span>Decision stage</span>
        <span className="muted">{lock.stage}</span>
      </div>
      {lock.sources_degraded && (
        <div className="row">
          <span>Data sources</span>
          <span className="state-warn">degraded — some inputs unreadable</span>
        </div>
      )}
    </section>
  )
}
