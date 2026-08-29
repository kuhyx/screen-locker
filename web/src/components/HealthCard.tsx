import { formatAge } from '../format'
import type { HealthPayload } from '../types'

interface Props {
  readonly health: HealthPayload
}

/**
 * Whether the locker could actually fire.
 *
 * Every row here is something that once went wrong silently: a timer systemd
 * deleted to break an ordering cycle, a disarm marker nobody removed, a log
 * that stopped being written. Absences are rendered as values so they cannot
 * be mistaken for good news.
 */
export function HealthCard({ health }: Props) {
  const armedClass = health.armed ? 'state-ok' : 'state-lock'
  return (
    <section className="card" aria-labelledby="health-heading">
      <h2 id="health-heading">Health</h2>
      {!health.timers_checked && (
        <p className="state-warn">
          {'systemctl unavailable — arming was NOT checked. This is not a pass.'}
        </p>
      )}
      <div className="row">
        <span>Enforcement</span>
        <span className={armedClass}>{health.armed ? 'armed' : 'NOT armed'}</span>
      </div>
      {health.disarmed && (
        <div className="row">
          <span>Disarm marker</span>
          <span className="state-lock">{`present at ${health.disarm_marker}`}</span>
        </div>
      )}
      {health.timers.map((timer) => (
        <div className="row" key={timer.name}>
          <span>{timer.name}</span>
          <span className={timer.armed ? 'state-ok' : 'state-lock'}>
            {timer.armed ? 'enabled and scheduled' : timer.describe}
          </span>
        </div>
      ))}
      <div className="row">
        <span>Workout log written</span>
        <span className="muted">{`${formatAge(health.log_age_seconds)} ago`}</span>
      </div>
      <div className="row">
        <span>Last decision recorded</span>
        <span className="muted">
          {`${formatAge(health.last_decision_age_seconds)} ago`}
        </span>
      </div>
    </section>
  )
}
