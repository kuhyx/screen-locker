import { budgetHours, describeReason, formatAge, formatStamp } from './format'
import type {
  Decision,
  DecisionsPayload,
  HealthPayload,
  StatusPayload,
} from './types'

type Child = Node | string

/** Build an element; strings become text nodes, never markup. */
function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  classes: string | null,
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  if (classes !== null) node.className = classes
  node.append(...children)
  return node
}

function row(label: string, ...value: Child[]): HTMLDivElement {
  return el('div', 'row', el('span', null, label), el('span', null, ...value))
}

function styledRow(
  label: string,
  classes: string,
  text: string,
): HTMLDivElement {
  return row(label, el('span', classes, text))
}

/** The decision as it stands right now, in words rather than slugs. */
export function renderNow(slot: HTMLElement, status: StatusPayload): void {
  const {
    snapshot,
    gaming,
    compliance_state: state,
    queue_wait: queued,
    locker_running: running,
  } = status
  const { week, lock_explanation: lock } = snapshot
  const nodes: Node[] = [
    el(
      'p',
      `headline state-${state}`,
      lock.fired ? 'Lock would fire' : 'No lock',
    ),
    el('p', 'muted', lock.reason),
  ]
  if (lock.fired && queued !== null) {
    const holders = queued.blocked_by.join(', ')
    const minutes = String(Math.round(queued.elapsed_seconds / 60))
    nodes.push(
      el(
        'p',
        'state-lock',
        `A locker run has already decided to lock and is waiting for ${holders} to release the screen (${minutes} min so far). The screen is held by ${holders}, not unlocked.`,
      ),
    )
  }
  if (lock.fired && queued === null && running === false) {
    nodes.push(
      el(
        'p',
        'state-lock',
        'No locker run is in progress right now, so nothing is enforcing this. The next timer tick will start one.',
      ),
    )
  }
  const counted = `${String(week.counted_count)}/${String(week.minimum)}`
  const togo = week.remaining > 0 ? ` — ${String(week.remaining)} to go` : ''
  nodes.push(
    row('This week', `${counted} workouts${togo}`),
    row('Today', gaming.reason),
    row(
      'Gaming budget today',
      el(
        'span',
        gaming.workout_today ? 'pill pill-ok' : 'pill pill-lock',
        `${String(budgetHours(gaming.workout_today))}h`,
      ),
      ' ',
      el(
        'span',
        'muted',
        gaming.workout_today
          ? 'earned by a workout logged today'
          : 'cut from 8h — no workout logged today',
      ),
    ),
    styledRow('Decision stage', 'muted', lock.stage),
  )
  if (lock.sources_degraded) {
    nodes.push(
      styledRow('Data sources', 'state-warn', 'degraded — some inputs unreadable'),
    )
  }
  slot.replaceChildren(...nodes)
}

/**
 * Whether the locker could actually fire.
 *
 * Every row here is something that once went wrong silently: a timer systemd
 * deleted to break an ordering cycle, a disarm marker nobody removed, a log
 * that stopped being written. Absences are rendered as values so they cannot
 * be mistaken for good news.
 */
export function renderHealth(slot: HTMLElement, health: HealthPayload): void {
  const nodes: Node[] = []
  if (!health.timers_checked) {
    nodes.push(
      el(
        'p',
        'state-warn',
        'systemctl unavailable — arming was NOT checked. This is not a pass.',
      ),
    )
  }
  nodes.push(
    styledRow(
      'Enforcement',
      health.armed ? 'state-ok' : 'state-lock',
      health.armed ? 'armed' : 'NOT armed',
    ),
  )
  if (health.disarmed) {
    nodes.push(
      styledRow('Disarm marker', 'state-lock', `present at ${health.disarm_marker}`),
    )
  }
  for (const timer of health.timers) {
    nodes.push(
      styledRow(
        timer.name,
        timer.armed ? 'state-ok' : 'state-lock',
        timer.armed ? 'enabled and scheduled' : timer.describe,
      ),
    )
  }
  nodes.push(
    styledRow('Workout log written', 'muted', `${formatAge(health.log_age_seconds)} ago`),
    styledRow(
      'Last decision recorded',
      'muted',
      `${formatAge(health.last_decision_age_seconds)} ago`,
    ),
  )
  slot.replaceChildren(...nodes)
}

function decisionRow(decision: Decision): HTMLTableRowElement {
  const when = el('td', null, decision.local_time ?? formatStamp(decision.timestamp))
  if (decision.repeat_count !== undefined && decision.repeat_count > 1) {
    const last =
      decision.local_last_time ??
      formatStamp(decision.last_timestamp ?? decision.timestamp)
    when.append(el('div', 'muted', `×${String(decision.repeat_count)}, last ${last}`))
  }
  let outcome = decision.locked ? 'locked' : 'no lock'
  if (decision.locked === null) outcome = '—'
  const why = el('td', null, describeReason(decision.reason))
  if (decision.also !== undefined && decision.also !== '') {
    why.append(el('div', 'muted', `also: ${decision.also}`))
  }
  const week =
    decision.weekly_count === undefined
      ? ''
      : `${String(decision.weekly_count)}/${String(decision.weekly_required ?? 0)}`
  return el(
    'tr',
    null,
    when,
    el('td', decision.locked === true ? 'state-lock' : 'muted', outcome),
    why,
    el('td', 'muted', week),
  )
}

/**
 * The decision history.
 *
 * This is the view that would have surfaced the 2026-08-29 bug without anyone
 * reading the journal: every half-hourly tick recorded
 * `weekly_minimum_met 5/5` while the real total was three.
 */
export function renderWhy(slot: HTMLElement, decisions: DecisionsPayload): void {
  const header = el('tr', null)
  for (const title of ['When', 'Outcome', 'Reason', 'Week']) {
    const th = el('th', null, title)
    th.scope = 'col'
    header.append(th)
  }
  const shown = `Showing ${String(decisions.returned)} of ${String(decisions.total)} recorded decisions, newest first.`
  slot.replaceChildren(
    el('p', 'muted', shown),
    el(
      'table',
      null,
      el('thead', null, header),
      el('tbody', null, ...decisions.decisions.map(decisionRow)),
    ),
  )
}

/**
 * Shown rather than swallowed: a UI that silently keeps rendering stale data
 * is the same failure the locker itself had.
 */
export function renderErrors(
  slot: HTMLElement,
  messages: readonly string[],
): void {
  slot.replaceChildren(
    ...[...new Set(messages)].map((message) => el('div', null, message)),
  )
  slot.hidden = messages.length === 0
}
