import { within } from '@testing-library/dom'
import { describe, expect, it } from 'vitest'
import { renderErrors, renderHealth } from './render'
import { makeSlot } from './test/dom'
import { makeHealth } from './test/factories'
import type { HealthPayload } from './types'

function show(over: Partial<HealthPayload> = {}) {
  const slot = makeSlot()
  renderHealth(slot, makeHealth(over))
  return within(slot)
}

describe('renderHealth', () => {
  it('reports an armed locker', () => {
    const view = show()
    expect(view.getByText('armed')).toHaveClass('state-ok')
    expect(view.getByText('enabled and scheduled')).toBeInTheDocument()
  })

  it('says an unchecked arming state is NOT a pass', () => {
    const view = show({ timers_checked: false, timers: [], armed: false })
    expect(view.getByText(/This is not a pass/)).toBeInTheDocument()
  })

  it('shows the disarm marker when enforcement is switched off', () => {
    const view = show({ disarmed: true, armed: false })
    expect(view.getByText(/present at/)).toBeInTheDocument()
    expect(view.getByText('NOT armed')).toHaveClass('state-lock')
  })

  it('shows a disarmed timer with its own reason', () => {
    const view = show({
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
    })
    expect(
      view.getByText('DISARMED workout-locker.timer: not enabled'),
    ).toBeInTheDocument()
  })

  it('renders unknown ages rather than hiding them', () => {
    const view = show({ log_age_seconds: null, last_decision_age_seconds: null })
    expect(view.getAllByText('unknown ago')).toHaveLength(2)
  })

  it('formats known ages', () => {
    const view = show()
    expect(view.getByText('1h ago')).toBeInTheDocument()
    expect(view.getByText('2m ago')).toBeInTheDocument()
  })
})

describe('renderErrors', () => {
  it('shows each distinct message once and unhides the slot', () => {
    const slot = makeSlot()
    slot.hidden = true
    renderErrors(slot, ['boom', 'boom', 'API returned 503 Unavailable'])
    expect(slot.hidden).toBe(false)
    expect(within(slot).getAllByText('boom')).toHaveLength(1)
    expect(slot).toHaveTextContent('API returned 503 Unavailable')
  })

  it('hides and empties the slot once everything recovers', () => {
    const slot = makeSlot()
    renderErrors(slot, ['boom'])
    renderErrors(slot, [])
    expect(slot.hidden).toBe(true)
    expect(slot).toBeEmptyDOMElement()
  })
})
