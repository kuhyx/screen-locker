import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { makeDecisions, makeHealth, makeStatus } from './test/factories'

function stubEndpoints(overrides: Record<string, unknown> = {}): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const body =
        url.startsWith('/api/status')
          ? (overrides.status ?? makeStatus())
          : url.startsWith('/api/health')
            ? (overrides.health ?? makeHealth())
            : (overrides.decisions ?? makeDecisions())
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders all three views once the endpoints answer', async () => {
    stubEndpoints()
    render(<App />)
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Now' })).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'Health' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Why' })).toBeInTheDocument()
  })

  it('shows a loading line before the first status arrives', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => undefined)))
    render(<App />)
    expect(screen.getByText('Reading status…')).toBeInTheDocument()
  })

  it('surfaces a failing endpoint instead of silently showing nothing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503, statusText: 'Unavailable' }),
    )
    render(<App />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.getByRole('alert')).toHaveTextContent('API returned 503')
  })
})
