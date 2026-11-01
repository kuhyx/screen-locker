import { within } from '@testing-library/dom'
import { describe, expect, it } from 'vitest'
import { renderNow } from './render'
import { makeSlot } from './test/dom'
import { makeStatus } from './test/factories'
import type { StatusPayload } from './types'

function show(status: StatusPayload) {
  const slot = makeSlot()
  renderNow(slot, status)
  return within(slot)
}

function withLock(over: Partial<StatusPayload['snapshot']['lock_explanation']>) {
  const base = makeStatus()
  return {
    ...base,
    snapshot: {
      ...base.snapshot,
      lock_explanation: { ...base.snapshot.lock_explanation, ...over },
    },
  }
}

describe('renderNow', () => {
  it('shows the cut budget and says why when no workout was logged', () => {
    const view = show(makeStatus())
    expect(view.getByText('No lock')).toBeInTheDocument()
    expect(view.getByText('6h')).toBeInTheDocument()
    expect(
      view.getByText('cut from 8h — no workout logged today'),
    ).toBeInTheDocument()
  })

  it('shows the earned budget once a workout is logged', () => {
    const view = show(
      makeStatus({
        gaming: {
          workout_today: true,
          credits_today: 1,
          reason: '1 counted workout(s) logged today',
        },
      }),
    )
    expect(view.getByText('8h')).toBeInTheDocument()
    expect(
      view.getByText('earned by a workout logged today'),
    ).toBeInTheDocument()
  })

  it('says the lock would fire when it would', () => {
    const view = show({
      ...withLock({
        fired: true,
        stage: 'would_lock',
        reason: 'No skip condition applies.',
      }),
      compliance_state: 'lock',
    })
    expect(view.getByText('Lock would fire')).toHaveClass('state-lock')
  })

  it('counts down the remaining workouts', () => {
    const view = show(makeStatus())
    expect(view.getByText(/3\/5 workouts — 2 to go/)).toBeInTheDocument()
  })

  it('drops the countdown once the week is met', () => {
    const base = makeStatus()
    const view = show({
      ...base,
      snapshot: {
        ...base.snapshot,
        week: { ...base.snapshot.week, counted_count: 5, remaining: 0 },
      },
    })
    expect(view.getByText(/5\/5 workouts$/)).toBeInTheDocument()
  })

  it('flags degraded sources rather than rendering a confident answer', () => {
    const view = show(withLock({ sources_degraded: true }))
    expect(view.getByText(/degraded/)).toBeInTheDocument()
  })

  it('renders markup-looking text as text, never as HTML', () => {
    const view = show(withLock({ reason: '<img src=x onerror=alert(1)>' }))
    expect(view.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
  })

  /**
   * "Lock would fire" is a statement about the decision, not about whether
   * anything is enforcing it. On 2026-08-30 the page said exactly that while
   * the machine had just rebooted and no locker process existed.
   */
  const firing = (over: Partial<StatusPayload> = {}): StatusPayload => ({
    ...withLock({ fired: true }),
    ...over,
  })

  it('says when a decided lock is queued behind another holder', () => {
    const view = show(
      firing({
        queue_wait: {
          blocked_by: ['wake_alarm'],
          elapsed_seconds: 10716,
          updated: '2026-08-30T09:01:05+00:00',
        },
        locker_running: true,
      }),
    )
    expect(view.getByText(/waiting for/)).toBeInTheDocument()
    expect(view.getByText(/179 min so far/)).toBeInTheDocument()
    expect(view.getByText(/not unlocked/)).toBeInTheDocument()
  })

  it('says when nothing is enforcing a lock it says would fire', () => {
    const view = show(firing({ locker_running: false }))
    expect(
      view.getByText(/No locker run is in progress right now/),
    ).toBeInTheDocument()
  })

  it('stays quiet when a run is up and unblocked', () => {
    const view = show(firing({ locker_running: true }))
    expect(view.queryByText(/No locker run is in progress/)).toBeNull()
    expect(view.queryByText(/waiting for/)).toBeNull()
  })

  it('says nothing about enforcement when no lock is due', () => {
    const view = show(makeStatus({ locker_running: false }))
    expect(view.queryByText(/No locker run is in progress/)).toBeNull()
  })

  it('replaces the previous render instead of appending', () => {
    const slot = makeSlot()
    renderNow(slot, makeStatus())
    renderNow(slot, makeStatus())
    expect(within(slot).getAllByText('No lock')).toHaveLength(1)
  })
})
