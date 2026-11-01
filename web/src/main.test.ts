import { screen, waitFor } from '@testing-library/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { startPage } from './main'
import { makeDecisions, makeHealth, makeStatus } from './test/factories'
import { SHELL } from './test/shell'

function stubEndpoints(failing: readonly string[] = []): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const name = ['status', 'health', 'decisions'].find((n) =>
        url.startsWith(`/api/${n}`),
      )
      if (name !== undefined && failing.includes(name)) {
        return Promise.resolve({ ok: false, status: 503, statusText: 'Unavailable' })
      }
      const body = url.startsWith('/api/status')
        ? makeStatus()
        : url.startsWith('/api/health')
          ? makeHealth()
          : makeDecisions()
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
    }),
  )
}

beforeEach(() => {
  document.body.innerHTML = SHELL
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

describe('startPage', () => {
  it('fills all three cards once the endpoints answer', async () => {
    stubEndpoints()
    const stop = startPage()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Now' })).toBeVisible()
    })
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Health' })).toBeVisible()
      expect(screen.getByRole('heading', { name: 'Why' })).toBeVisible()
    })
    expect(screen.getByText('No lock')).toBeVisible()
    expect(screen.getByText('armed')).toBeVisible()
    expect(screen.getByText('Skipped — weekly minimum already met')).toBeVisible()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByText('Reading status…')).not.toBeVisible()
    stop()
  })

  it('requests at most 200 decisions', () => {
    stubEndpoints()
    const stop = startPage()
    expect(fetch).toHaveBeenCalledWith('/api/decisions?limit=200')
    stop()
  })

  it('shows a loading line before the first status arrives', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => undefined)))
    const stop = startPage()
    expect(screen.getByText('Reading status…')).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Now' })).toBeNull()
    stop()
  })

  it('surfaces a failing endpoint instead of silently showing nothing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503, statusText: 'Unavailable' }),
    )
    const stop = startPage()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeVisible()
    })
    expect(screen.getByRole('alert')).toHaveTextContent('API returned 503')
    stop()
  })

  it('keeps the healthy cards and reports the one that failed', async () => {
    stubEndpoints(['health'])
    const stop = startPage()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeVisible()
    })
    expect(screen.getByRole('heading', { name: 'Now' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Health' })).toBeNull()
    stop()
  })

  it('stops polling when the returned function is called', async () => {
    vi.useFakeTimers()
    stubEndpoints()
    const stop = startPage()
    stop()
    vi.mocked(fetch).mockClear()
    await vi.advanceTimersByTimeAsync(60000)
    expect(fetch).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('fails loudly when the page shell is missing a piece', () => {
    document.body.replaceChildren()
    expect(() => startPage()).toThrow(/\[data-errors\] is missing/)
  })
})
