export const POLL_MS = 15000

export interface PollResult<T> {
  readonly data: T | null
  readonly error: string | null
}

/**
 * Polls a fetcher, keeping the last good value on failure. The first load
 * always happens, even in a hidden tab (a guard there once left automation
 * tabs stuck on "loading"); only the interval pauses while hidden, and
 * becoming visible reloads at once.
 */
export class Poller<T> {
  readonly #fetcher: () => Promise<T>
  readonly #onUpdate: (result: PollResult<T>) => void
  readonly #intervalMs: number
  readonly #doc: Document
  #data: T | null = null
  #handle: ReturnType<typeof setInterval> | undefined
  #generation = 0

  constructor(
    fetcher: () => Promise<T>,
    onUpdate: (result: PollResult<T>) => void,
    intervalMs: number = POLL_MS,
    doc: Document = document,
  ) {
    this.#fetcher = fetcher
    this.#onUpdate = onUpdate
    this.#intervalMs = intervalMs
    this.#doc = doc
  }

  start(): void {
    this.stop()
    this.#doc.addEventListener('visibilitychange', this.#onVisibility)
    this.#load()
    if (!this.#doc.hidden) this.#schedule()
  }

  stop(): void {
    this.#generation += 1
    clearInterval(this.#handle)
    this.#doc.removeEventListener('visibilitychange', this.#onVisibility)
  }

  readonly #onVisibility = (): void => {
    clearInterval(this.#handle)
    if (this.#doc.hidden) return
    this.#load()
    this.#schedule()
  }

  #schedule(): void {
    this.#handle = setInterval(() => {
      this.#load()
    }, this.#intervalMs)
  }

  #load(): void {
    const generation = this.#generation
    this.#fetcher()
      .then((value) => {
        if (generation !== this.#generation) return
        this.#data = value
        this.#onUpdate({ data: value, error: null })
      })
      .catch((e: unknown) => {
        if (generation !== this.#generation) return
        this.#onUpdate({
          data: this.#data,
          error: e instanceof Error ? e.message : String(e),
        })
      })
  }
}
