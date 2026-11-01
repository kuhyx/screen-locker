import { fetchDecisions, fetchHealth, fetchStatus } from './api'
import { Poller, type PollResult } from './poll'
import { renderErrors, renderHealth, renderNow, renderWhy } from './render'

export const DECISION_LIMIT = 200

function find(doc: Document, selector: string): HTMLElement {
  const found = doc.querySelector<HTMLElement>(selector)
  if (found === null) throw new Error(`${selector} is missing from the page`)
  return found
}

/** Wires the three pollers to the three card shells in `index.astro`. */
export function startPage(doc: Document = document): () => void {
  const errorSlot = find(doc, '[data-errors]')
  const loading = find(doc, '[data-loading]')
  const failures = new Map<string, string>()

  function bind<T>(
    name: string,
    fetcher: () => Promise<T>,
    render: (slot: HTMLElement, data: T) => void,
  ): Poller<T> {
    const card = find(doc, `[data-card="${name}"]`)
    const slot = find(doc, `[data-card="${name}"] [data-slot]`)
    return new Poller(
      fetcher,
      ({ data, error }: PollResult<T>) => {
        if (data !== null) {
          render(slot, data)
          card.hidden = false
        }
        if (error === null) failures.delete(name)
        else failures.set(name, error)
        renderErrors(errorSlot, [...failures.values()])
      },
      undefined,
      doc,
    )
  }

  const pollers = [
    bind('now', fetchStatus, (slot, status) => {
      loading.hidden = true
      renderNow(slot, status)
    }),
    bind('health', fetchHealth, renderHealth),
    bind('why', () => fetchDecisions(DECISION_LIMIT), renderWhy),
  ]
  for (const poller of pollers) poller.start()
  return () => {
    for (const poller of pollers) poller.stop()
  }
}
