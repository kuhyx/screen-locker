import type { DecisionsPayload, HealthPayload, StatusPayload } from './types'

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(path)
  if (!resp.ok) {
    throw new Error(`API returned ${String(resp.status)} ${resp.statusText}`)
  }
  return (await resp.json()) as T
}

export function fetchStatus(): Promise<StatusPayload> {
  return getJson<StatusPayload>('/api/status')
}

export function fetchDecisions(limit: number): Promise<DecisionsPayload> {
  return getJson<DecisionsPayload>(`/api/decisions?limit=${String(limit)}`)
}

export function fetchHealth(): Promise<HealthPayload> {
  return getJson<HealthPayload>('/api/health')
}
