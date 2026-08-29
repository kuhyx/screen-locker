import { useEffect, useState } from 'react'

export const POLL_MS = 15000

interface PollResult<T> {
  readonly data: T | null
  readonly error: string | null
}

/**
 * Poll a fetcher on an interval, keeping the last good value on failure.
 *
 * Deliberately has no `document.hidden` guard. The enforcer's equivalent hook
 * had one and it swallowed the first load, leaving automation-driven tabs stuck
 * on the loading message forever; see steam-backlog-enforcer useBudgetPoll.
 */
export function usePoll<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = POLL_MS,
): PollResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () => {
      fetcher()
        .then((value) => {
          if (!cancelled) {
            setData(value)
            setError(null)
          }
        })
        .catch((e: unknown) => {
          if (!cancelled) {
            setError(e instanceof Error ? e.message : String(e))
          }
        })
    }
    load()
    const handle = setInterval(load, intervalMs)
    return () => {
      cancelled = true
      clearInterval(handle)
    }
  }, [fetcher, intervalMs])

  return { data, error }
}
