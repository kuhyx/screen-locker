import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { POLL_MS, usePoll } from './useStatusPoll'

afterEach(() => {
  vi.useRealTimers()
})

describe('usePoll', () => {
  it('loads immediately rather than waiting for the first interval', async () => {
    const fetcher = vi.fn().mockResolvedValue('value')
    const { result } = renderHook(() => usePoll(fetcher))
    await waitFor(() => {
      expect(result.current.data).toBe('value')
    })
    expect(result.current.error).toBeNull()
  })

  it('surfaces an Error message', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => usePoll(fetcher))
    await waitFor(() => {
      expect(result.current.error).toBe('boom')
    })
  })

  it('stringifies a non-Error rejection instead of rendering nothing', async () => {
    const fetcher = vi.fn().mockRejectedValue('plain string')
    const { result } = renderHook(() => usePoll(fetcher))
    await waitFor(() => {
      expect(result.current.error).toBe('plain string')
    })
  })

  it('clears a previous error once a load succeeds again', async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue('ok')
    const { result, rerender } = renderHook(
      ({ interval }: { interval: number }) => usePoll(fetcher, interval),

      { initialProps: { interval: 100000 } },
    )
    await waitFor(() => {
      expect(result.current.error).toBe('boom')
    })
    rerender({ interval: 200000 })
    await waitFor(() => {
      expect(result.current.data).toBe('ok')
    })
    expect(result.current.error).toBeNull()
  })

  it('polls again on the interval', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn().mockResolvedValue('value')
    renderHook(() => usePoll(fetcher, 1000))
    expect(fetcher).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(2000)
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('stops updating after unmount', async () => {
    const fetcher = vi.fn().mockResolvedValue('value')
    const { result, unmount } = renderHook(() => usePoll(fetcher))
    unmount()
    await Promise.resolve()
    expect(result.current.data).toBeNull()
  })

  it('ignores a rejection that lands after unmount', async () => {
    // The cancelled guard in the catch path: without it React warns about a
    // state update on an unmounted component, and a stale error would stick.
    let reject: (reason: Error) => void = () => undefined
    const fetcher = vi.fn(
      () =>
        new Promise<string>((_resolve, rej) => {
          reject = rej
        }),
    )
    const { result, unmount } = renderHook(() => usePoll(fetcher))
    unmount()
    reject(new Error('late failure'))
    await Promise.resolve()
    expect(result.current.error).toBeNull()
  })

  it('exposes a sane default interval', () => {
    expect(POLL_MS).toBeGreaterThan(0)
  })
})
