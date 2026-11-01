import { afterEach, describe, expect, it, vi } from 'vitest'
import { POLL_MS, Poller, type PollResult } from './poll'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function setHidden(hidden: boolean): void {
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(hidden)
  document.dispatchEvent(new Event('visibilitychange'))
}

function make<T>(fetcher: () => Promise<T>, intervalMs = 1000) {
  const updates: PollResult<T>[] = []
  const poller = new Poller(fetcher, (r) => updates.push(r), intervalMs)
  return { poller, updates }
}

describe('Poller', () => {
  it('has a 15 s default interval', () => {
    expect(POLL_MS).toBe(15000)
  })

  it('loads immediately rather than waiting for the first interval', async () => {
    const { poller, updates } = make(() => Promise.resolve('value'))
    poller.start()
    await vi.waitFor(() => {
      expect(updates).toEqual([{ data: 'value', error: null }])
    })
    poller.stop()
  })

  it('surfaces an Error message', async () => {
    const { poller, updates } = make(() => Promise.reject(new Error('boom')))
    poller.start()
    await vi.waitFor(() => {
      expect(updates).toEqual([{ data: null, error: 'boom' }])
    })
    poller.stop()
  })

  it('stringifies a non-Error rejection instead of rendering nothing', async () => {
    const { poller, updates } = make(vi.fn().mockRejectedValue('plain string'))
    poller.start()
    await vi.waitFor(() => {
      expect(updates).toEqual([{ data: null, error: 'plain string' }])
    })
    poller.stop()
  })

  it('keeps the last good value on failure and clears the error on recovery', async () => {
    vi.useFakeTimers()
    const fetcher = vi
      .fn<() => Promise<string>>()
      .mockResolvedValueOnce('first')
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue('again')
    const { poller, updates } = make(fetcher)
    poller.start()
    await vi.advanceTimersByTimeAsync(2000)
    poller.stop()
    expect(updates).toEqual([
      { data: 'first', error: null },
      { data: 'first', error: 'boom' },
      { data: 'again', error: null },
    ])
  })

  it('polls again on the interval', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn(() => Promise.resolve('value'))
    const { poller } = make(fetcher)
    poller.start()
    expect(fetcher).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(2000)
    expect(fetcher).toHaveBeenCalledTimes(3)
    poller.stop()
  })

  it('stops polling and drops an in-flight result after stop()', async () => {
    vi.useFakeTimers()
    let resolve: (value: string) => void = () => undefined
    const fetcher = vi.fn(
      () =>
        new Promise<string>((r) => {
          resolve = r
        }),
    )
    const { poller, updates } = make(fetcher)
    poller.start()
    poller.stop()
    resolve('late')
    await vi.advanceTimersByTimeAsync(5000)
    expect(updates).toEqual([])
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('drops a rejection that lands after stop()', async () => {
    let reject: (reason: Error) => void = () => undefined
    const fetcher = vi.fn(
      () =>
        new Promise<string>((_resolve, rej) => {
          reject = rej
        }),
    )
    const { poller, updates } = make(fetcher)
    poller.start()
    poller.stop()
    reject(new Error('late'))
    await Promise.resolve()
    await Promise.resolve()
    expect(updates).toEqual([])
  })

  it('start() twice does not double the interval', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn(() => Promise.resolve('value'))
    const { poller } = make(fetcher)
    poller.start()
    poller.start()
    fetcher.mockClear()
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetcher).toHaveBeenCalledTimes(1)
    poller.stop()
  })

  it('pauses the interval while hidden and reloads on becoming visible', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn(() => Promise.resolve('value'))
    const { poller } = make(fetcher)
    poller.start()
    setHidden(true)
    fetcher.mockClear()
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetcher).not.toHaveBeenCalled()
    setHidden(false)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetcher).toHaveBeenCalledTimes(2)
    poller.stop()
  })

  it('still does the first load when started in a hidden tab', async () => {
    vi.useFakeTimers()
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    const fetcher = vi.fn(() => Promise.resolve('value'))
    const { poller, updates } = make(fetcher)
    poller.start()
    await vi.advanceTimersByTimeAsync(5000)
    expect(updates).toEqual([{ data: 'value', error: null }])
    expect(fetcher).toHaveBeenCalledTimes(1)
    poller.stop()
  })

  it('ignores visibility changes after stop()', () => {
    const fetcher = vi.fn(() => Promise.resolve('value'))
    const { poller } = make(fetcher)
    poller.start()
    poller.stop()
    fetcher.mockClear()
    setHidden(false)
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('uses the shared document and 15 s interval by default', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn(() => Promise.resolve('value'))
    const poller = new Poller(fetcher, () => undefined)
    poller.start()
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(fetcher).toHaveBeenCalledTimes(2)
    poller.stop()
  })
})
