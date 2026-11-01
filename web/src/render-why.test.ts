import { within } from '@testing-library/dom'
import { describe, expect, it } from 'vitest'
import { renderWhy } from './render'
import { makeSlot } from './test/dom'
import { makeDecisions } from './test/factories'
import type { DecisionsPayload } from './types'

function show(over: Partial<DecisionsPayload> = {}) {
  const slot = makeSlot()
  renderWhy(slot, makeDecisions(over))
  return within(slot)
}

describe('renderWhy', () => {
  it('renders the decision that hid the 2026-08-29 bug', () => {
    const view = show()
    expect(
      view.getByText('Skipped — weekly minimum already met'),
    ).toBeInTheDocument()
    expect(view.getByText('5/5')).toBeInTheDocument()
    expect(view.getByText('also: early_bird_window_active')).toBeInTheDocument()
  })

  it('has the four column headers', () => {
    const headers = show().getAllByRole('columnheader')
    expect(headers.map((h) => h.textContent)).toEqual([
      'When',
      'Outcome',
      'Reason',
      'Week',
    ])
  })

  it('says how much of the trail is shown', () => {
    expect(show().getByText(/Showing 1 of 3000/)).toBeInTheDocument()
  })

  it('marks a decision that actually locked', () => {
    const view = show({
      decisions: [
        {
          timestamp: '2026-08-30T20:00:00+00:00',
          locked: true,
          reason: 'enforced',
        },
      ],
    })
    expect(view.getByText('locked')).toHaveClass('state-lock')
  })

  it('renders a no-decision run as a dash with no week column', () => {
    const view = show({
      decisions: [
        {
          timestamp: '2026-08-29T20:00:05+00:00',
          locked: null,
          reason: 'mode_makes_no_decision',
          mode: '--sync-only',
        },
      ],
    })
    expect(view.getByText('—')).toBeInTheDocument()
    expect(
      view.getByText('No decision (status or sync-only run)'),
    ).toBeInTheDocument()
  })

  it('omits the also line when there is none', () => {
    const view = show({
      decisions: [
        {
          timestamp: '2026-08-30T20:00:00+00:00',
          locked: false,
          reason: 'relaxed_day',
          also: '',
          weekly_count: 2,
        },
      ],
    })
    expect(view.queryByText(/^also:/)).not.toBeInTheDocument()
    // weekly_required missing falls back to 0 rather than rendering undefined.
    expect(view.getByText('2/0')).toBeInTheDocument()
  })

  /**
   * A restart loop wrote ~1693 identical records on 2026-08-30 and evicted
   * the whole trail. They now collapse into one row, which must not then
   * read as a gap in history.
   */
  it('shows how many times a collapsed row repeated, and when it last did', () => {
    const view = show({
      decisions: [
        {
          timestamp: '2026-08-30T00:02:00+00:00',
          locked: true,
          reason: 'enforced',
          repeat_count: 1693,
          last_timestamp: '2026-08-30T03:05:00+00:00',
          local_time: 'Aug 30, 02:02',
          local_last_time: 'Aug 30, 05:05',
        },
      ],
    })
    expect(view.getByText('Aug 30, 02:02')).toBeInTheDocument()
    expect(view.getByText(/×1693, last Aug 30, 05:05/)).toBeInTheDocument()
  })

  it('prefers the server-rendered local time over the browser clock', () => {
    // LibreWolf's resistFingerprinting pins JS Date to UTC, which rendered a
    // 14:00 CEST decision as "12:00 PM" on 2026-08-30.
    const view = show({
      decisions: [
        {
          timestamp: '2026-08-30T12:00:05+00:00',
          locked: true,
          reason: 'enforced',
          local_time: 'Aug 30, 14:00',
        },
      ],
    })
    expect(view.getByText('Aug 30, 14:00')).toBeInTheDocument()
  })

  it('falls back to formatting the ISO stamp when the server sent none', () => {
    const view = show({
      decisions: [
        {
          timestamp: '2026-08-30T12:00:05+00:00',
          locked: true,
          reason: 'enforced',
          repeat_count: 3,
        },
      ],
    })
    expect(view.getByText(/×3, last/)).toBeInTheDocument()
  })

  it('falls back to the first stamp when a collapsed row has no last one', () => {
    const view = show({
      decisions: [
        {
          timestamp: '2026-08-30T12:00:05+00:00',
          locked: true,
          reason: 'enforced',
          repeat_count: 2,
          last_timestamp: '2026-08-30T13:00:05+00:00',
        },
      ],
    })
    expect(view.getByText(/×2, last/)).toBeInTheDocument()
  })

  it('adds no repeat note to a row that happened once', () => {
    expect(show().queryByText(/×/)).toBeNull()
  })
})
