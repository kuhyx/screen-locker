import { describe, expect, it } from 'vitest'
import { budgetHours, describeReason, formatAge, formatStamp } from './format'

describe('formatAge', () => {
  it('reports a missing age as unknown, never as fresh', () => {
    expect(formatAge(null)).toBe('unknown')
  })

  it('handles a clock skew rather than printing a negative age', () => {
    expect(formatAge(-5)).toBe('in the future')
  })

  it.each([
    [30, '30s'],
    [90, '1m'],
    [3600, '1h'],
    [90000, '1d'],
  ])('renders %i seconds as %s', (seconds, expected) => {
    expect(formatAge(seconds)).toBe(expected)
  })
})

describe('formatStamp', () => {
  it('renders a valid ISO timestamp', () => {
    expect(formatStamp('2026-08-29T20:01:02+00:00')).toMatch(/Aug/)
  })

  it('passes an unparsable value through unchanged', () => {
    expect(formatStamp('not a date')).toBe('not a date')
  })
})

describe('describeReason', () => {
  it('spells out a known slug', () => {
    expect(describeReason('weekly_minimum_met')).toBe(
      'Skipped — weekly minimum already met',
    )
  })

  it('degrades gracefully for a slug added on the Python side later', () => {
    expect(describeReason('some_new_reason')).toBe('some new reason')
  })
})

describe('budgetHours', () => {
  it('gives 8h when a workout was logged today', () => {
    expect(budgetHours(true)).toBe(8)
  })

  it('cuts to 6h when none was', () => {
    expect(budgetHours(false)).toBe(6)
  })
})
