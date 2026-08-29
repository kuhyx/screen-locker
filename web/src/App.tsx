import { useCallback } from 'react'
import { HealthCard } from './components/HealthCard'
import { NowCard } from './components/NowCard'
import { WhyTable } from './components/WhyTable'
import { fetchDecisions, fetchHealth, fetchStatus } from './api'
import { usePoll } from './useStatusPoll'

const DECISION_LIMIT = 200

export function App() {
  // Stable identities: usePoll re-subscribes whenever the fetcher changes, and
  // an inline arrow would restart every interval on each render.
  const decisionFetcher = useCallback(() => fetchDecisions(DECISION_LIMIT), [])
  const status = usePoll(fetchStatus)
  const decisions = usePoll(decisionFetcher)
  const health = usePoll(fetchHealth)

  const errors = [status.error, decisions.error, health.error].filter(
    (e): e is string => e !== null,
  )

  return (
    <main>
      <h1>Screen locker</h1>
      {errors.length > 0 && (
        <div className="error" role="alert">
          {/* Shown rather than swallowed: a UI that silently keeps rendering
              stale data is the same failure the locker itself had. */}
          {errors.map((message) => (
            <div key={message}>{message}</div>
          ))}
        </div>
      )}
      {status.data === null ? (
        <p className="muted">Reading status…</p>
      ) : (
        <NowCard status={status.data} />
      )}
      {health.data !== null && <HealthCard health={health.data} />}
      {decisions.data !== null && <WhyTable decisions={decisions.data} />}
    </main>
  )
}
