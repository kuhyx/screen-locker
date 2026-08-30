import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NowCard } from './NowCard'
import { makeStatus } from '../test/factories'
import type { StatusPayload } from '../types'

describe('NowCard', () => {
  it('shows the cut budget and says why when no workout was logged', () => {
    render(<NowCard status={makeStatus()} />)
    expect(screen.getByText('No lock')).toBeInTheDocument()
    expect(screen.getByText('6h')).toBeInTheDocument()
    expect(
      screen.getByText('cut from 8h — no workout logged today'),
    ).toBeInTheDocument()
  })

  it('shows the earned budget once a workout is logged', () => {
    const status = makeStatus({
      gaming: {
        workout_today: true,
        credits_today: 1,
        reason: '1 counted workout(s) logged today',
      },
    })
    render(<NowCard status={status} />)
    expect(screen.getByText('8h')).toBeInTheDocument()
    expect(
      screen.getByText('earned by a workout logged today'),
    ).toBeInTheDocument()
  })

  it('says the lock would fire when it would', () => {
    const base = makeStatus()
    render(
      <NowCard
        status={{
          ...base,
          compliance_state: 'lock',
          snapshot: {
            ...base.snapshot,
            lock_explanation: {
              ...base.snapshot.lock_explanation,
              fired: true,
              stage: 'would_lock',
              reason: 'No skip condition applies.',
            },
          },
        }}
      />,
    )
    expect(screen.getByText('Lock would fire')).toBeInTheDocument()
  })

  it('counts down the remaining workouts', () => {
    render(<NowCard status={makeStatus()} />)
    expect(screen.getByText(/3\/5 workouts — 2 to go/)).toBeInTheDocument()
  })

  it('drops the countdown once the week is met', () => {
    const base = makeStatus()
    render(
      <NowCard
        status={{
          ...base,
          snapshot: {
            ...base.snapshot,
            week: { ...base.snapshot.week, counted_count: 5, remaining: 0 },
          },
        }}
      />,
    )
    expect(screen.getByText(/5\/5 workouts$/)).toBeInTheDocument()
  })

  it('flags degraded sources rather than rendering a confident answer', () => {
    const base = makeStatus()
    render(
      <NowCard
        status={{
          ...base,
          snapshot: {
            ...base.snapshot,
            lock_explanation: {
              ...base.snapshot.lock_explanation,
              sources_degraded: true,
            },
          },
        }}
      />,
    )
    expect(screen.getByText(/degraded/)).toBeInTheDocument()
  })

  /**
   * "Lock would fire" is a statement about the decision, not about whether
   * anything is enforcing it. On 2026-08-30 the page said exactly that while
   * the machine had just rebooted and no locker process existed.
   */
  const firing = (over: Partial<StatusPayload> = {}) => {
    const base = makeStatus()
    return {
      ...base,
      snapshot: {
        ...base.snapshot,
        lock_explanation: { ...base.snapshot.lock_explanation, fired: true },
      },
      ...over,
    }
  }

  it('says when a decided lock is queued behind another holder', () => {
    render(
      <NowCard
        status={firing({
          queue_wait: {
            blocked_by: ['wake_alarm'],
            elapsed_seconds: 10716,
            updated: '2026-08-30T09:01:05+00:00',
          },
          locker_running: true,
        })}
      />,
    )
    expect(screen.getByText(/waiting for/)).toBeInTheDocument()
    expect(screen.getByText(/179 min so far/)).toBeInTheDocument()
    expect(screen.getByText(/not unlocked/)).toBeInTheDocument()
  })

  it('says when nothing is enforcing a lock it says would fire', () => {
    render(<NowCard status={firing({ locker_running: false })} />)
    expect(
      screen.getByText(/No locker run is in progress right now/),
    ).toBeInTheDocument()
  })

  it('stays quiet when a run is up and unblocked', () => {
    render(<NowCard status={firing({ locker_running: true })} />)
    expect(screen.queryByText(/No locker run is in progress/)).toBeNull()
    expect(screen.queryByText(/waiting for/)).toBeNull()
  })

  it('says nothing about enforcement when no lock is due', () => {
    render(<NowCard status={makeStatus({ locker_running: false })} />)
    expect(screen.queryByText(/No locker run is in progress/)).toBeNull()
  })
})
