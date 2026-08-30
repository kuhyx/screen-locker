import { describeReason, formatStamp } from '../format'
import type { DecisionsPayload } from '../types'

interface Props {
  readonly decisions: DecisionsPayload
}

/**
 * The decision history.
 *
 * This is the view that would have surfaced the 2026-08-29 bug without anyone
 * reading the journal: every half-hourly tick recorded
 * `weekly_minimum_met 5/5` while the real total was three.
 */
export function WhyTable({ decisions }: Props) {
  return (
    <section className="card" aria-labelledby="why-heading">
      <h2 id="why-heading">Why</h2>
      <p className="muted">
        Showing {decisions.returned} of {decisions.total} recorded decisions,
        newest first.
      </p>
      <table>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Outcome</th>
            <th scope="col">Reason</th>
            <th scope="col">Week</th>
          </tr>
        </thead>
        <tbody>
          {decisions.decisions.map((decision, index) => (
            <tr key={`${decision.timestamp}-${String(index)}`}>
              <td>
                {decision.local_time ?? formatStamp(decision.timestamp)}
                {decision.repeat_count !== undefined &&
                  decision.repeat_count > 1 && (
                    <div className="muted">
                      ×{decision.repeat_count}, last{' '}
                      {decision.local_last_time ??
                        formatStamp(
                          decision.last_timestamp ?? decision.timestamp,
                        )}
                    </div>
                  )}
              </td>
              <td className={decision.locked === true ? 'state-lock' : 'muted'}>
                {decision.locked === null
                  ? '—'
                  : decision.locked
                    ? 'locked'
                    : 'no lock'}
              </td>
              <td>
                {describeReason(decision.reason)}
                {decision.also !== undefined && decision.also !== '' && (
                  <div className="muted">also: {decision.also}</div>
                )}
              </td>
              <td className="muted">
                {decision.weekly_count === undefined
                  ? ''
                  : `${String(decision.weekly_count)}/${String(
                      decision.weekly_required ?? 0,
                    )}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
