import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchDecisions, fetchHealth, fetchStatus } from './api'

function mockFetch(response: Partial<Response>): void {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api', () => {
  it('returns the parsed body for a 200', async () => {
    mockFetch({ ok: true, json: () => Promise.resolve({ total: 1 }) })
    await expect(fetchDecisions(5)).resolves.toStrictEqual({ total: 1 })
  })

  it('passes the limit through in the query string', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', spy)
    await fetchDecisions(42)
    expect(spy).toHaveBeenCalledWith('/api/decisions?limit=42')
  })

  it('throws with the status text on a failure, rather than returning empty', async () => {
    mockFetch({ ok: false, status: 500, statusText: 'Internal Server Error' })
    await expect(fetchStatus()).rejects.toThrow('API returned 500 Internal Server Error')
  })

  it('requests the health endpoint', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', spy)
    await fetchHealth()
    expect(spy).toHaveBeenCalledWith('/api/health')
  })

  it('requests the status endpoint', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', spy)
    await fetchStatus()
    expect(spy).toHaveBeenCalledWith('/api/status')
  })
})
