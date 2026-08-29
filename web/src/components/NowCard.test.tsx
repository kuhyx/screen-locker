import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NowCard } from './NowCard'
import { makeStatus } from '../test/factories'

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
              stage: 'full_lock_pending_heat_check',
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
})
