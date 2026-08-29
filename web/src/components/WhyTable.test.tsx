import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WhyTable } from './WhyTable'
import { makeDecisions } from '../test/factories'

describe('WhyTable', () => {
  it('renders the decision that hid the 2026-08-29 bug', () => {
    render(<WhyTable decisions={makeDecisions()} />)
    expect(
      screen.getByText('Skipped — weekly minimum already met'),
    ).toBeInTheDocument()
    expect(screen.getByText('5/5')).toBeInTheDocument()
    expect(screen.getByText('also: early_bird_window_active')).toBeInTheDocument()
  })

  it('says how much of the trail is shown', () => {
    render(<WhyTable decisions={makeDecisions()} />)
    expect(screen.getByText(/Showing 1 of 3000/)).toBeInTheDocument()
  })

  it('marks a decision that actually locked', () => {
    render(
      <WhyTable
        decisions={makeDecisions({
          decisions: [
            {
              timestamp: '2026-08-30T20:00:00+00:00',
              locked: true,
              reason: 'enforced',
            },
          ],
        })}
      />,
    )
    expect(screen.getByText('locked')).toBeInTheDocument()
  })

  it('renders a no-decision run as a dash with no week column', () => {
    render(
      <WhyTable
        decisions={makeDecisions({
          decisions: [
            {
              timestamp: '2026-08-29T20:00:05+00:00',
              locked: null,
              reason: 'mode_makes_no_decision',
              mode: '--sync-only',
            },
          ],
        })}
      />,
    )
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(
      screen.getByText('No decision (status or sync-only run)'),
    ).toBeInTheDocument()
  })

  it('omits the also line when there is none', () => {
    render(
      <WhyTable
        decisions={makeDecisions({
          decisions: [
            {
              timestamp: '2026-08-30T20:00:00+00:00',
              locked: false,
              reason: 'relaxed_day',
              also: '',
              weekly_count: 2,
            },
          ],
        })}
      />,
    )
    expect(screen.queryByText(/^also:/)).not.toBeInTheDocument()
    // weekly_required missing falls back to 0 rather than rendering undefined.
    expect(screen.getByText('2/0')).toBeInTheDocument()
  })
})
