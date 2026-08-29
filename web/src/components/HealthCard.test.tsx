import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HealthCard } from './HealthCard'
import { makeHealth } from '../test/factories'

describe('HealthCard', () => {
  it('reports an armed locker', () => {
    render(<HealthCard health={makeHealth()} />)
    expect(screen.getByText('armed')).toBeInTheDocument()
    expect(screen.getByText('enabled and scheduled')).toBeInTheDocument()
  })

  it('says an unchecked arming state is NOT a pass', () => {
    render(
      <HealthCard
        health={makeHealth({ timers_checked: false, timers: [], armed: false })}
      />,
    )
    expect(screen.getByText(/This is not a pass/)).toBeInTheDocument()
  })

  it('shows the disarm marker when enforcement is switched off', () => {
    render(<HealthCard health={makeHealth({ disarmed: true, armed: false })} />)
    expect(screen.getByText(/present at/)).toBeInTheDocument()
    expect(screen.getByText('NOT armed')).toBeInTheDocument()
  })

  it('shows a disarmed timer with its own reason', () => {
    render(
      <HealthCard
        health={makeHealth({
          armed: false,
          timers: [
            {
              name: 'workout-locker.timer',
              enabled: false,
              scheduled: false,
              armed: false,
              describe: 'DISARMED workout-locker.timer: not enabled',
            },
          ],
        })}
      />,
    )
    expect(
      screen.getByText('DISARMED workout-locker.timer: not enabled'),
    ).toBeInTheDocument()
  })

  it('renders unknown ages rather than hiding them', () => {
    render(
      <HealthCard
        health={makeHealth({
          log_age_seconds: null,
          last_decision_age_seconds: null,
        })}
      />,
    )
    expect(screen.getAllByText('unknown ago')).toHaveLength(2)
  })
})
