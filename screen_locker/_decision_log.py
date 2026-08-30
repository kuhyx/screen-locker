"""One structured, durable record of every lock decision the locker makes.

This module exists because of a multi-day outage that produced *no evidence*.
Between 2026-08-04 and 2026-08-17 the locker stopped enforcing, and the only
trace in the journal was its absence: ``workout-locker.service`` started, ran
for six seconds, exited ``0/SUCCESS``, and said nothing about why. Every
early-exit reason was logged at ``INFO``, and ``logging.basicConfig`` was only
ever called on the ``--sync-only`` path, so ``--production`` emitted no INFO at
all -- zero such lines since June.

Two things follow from that, and this module provides both:

* **A single grep-able line per run.** ``DECISION lock=no reason=... weekly=0/5``
  is one line a human or an agent can find without knowing the code, and it is
  emitted at ``WARNING`` when enforcement was skipped, because per CLAUDE.md an
  ``INFO``-level explanation of a non-action is a silent failure with extra
  steps.
* **A durable JSONL trail.** The journal rotates and is per-boot; a decision
  history that outlives it is what makes "when did this last actually enforce?"
  answerable in one command instead of a forensic session.

The file is deliberately outside the repo (see ``DECISION_LOG_FILE``): the
2026-07 privacy incident purged workout state JSONs from git history, and they
must never be re-tracked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING

from screen_locker._armed_state import locker_unit_active
from screen_locker._decision_trail import (
    DECISION_LOG_FILE,
    DECISION_LOG_MAX_ENTRIES,
    append_record,
)
from screen_locker._queue_state import read_queue_wait

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "DECISION_LOG_FILE",
    "DECISION_LOG_MAX_ENTRIES",
    "LockDecision",
    "read_decisions",
    "record_decision",
]

_logger = logging.getLogger(__name__)

# Both live in _decision_trail (which owns the writer) and are re-exported
# here, where every reader already looks for them.


@dataclass(frozen=True)
class LockDecision:
    """Why the locker did or did not enforce on one run.

    ``reason`` is a stable machine-readable slug (``early_bird_pending``,
    ``weekly_minimum_met``, ``enforced``...), not prose, so it can be grepped
    and counted across runs. ``detail`` carries the human sentence.
    """

    locked: bool
    reason: str
    detail: str = ""
    weekly_count: int | None = None
    weekly_required: int | None = None
    extra: dict[str, object] = field(default_factory=dict)

    def as_line(self) -> str:
        """Render the single grep-able summary line.

        Keys are ``key=value`` pairs so the line stays readable by eye and
        parseable by ``awk``/``grep -o`` without a JSON decoder.
        """
        parts = [
            "DECISION",
            f"lock={'yes' if self.locked else 'no'}",
            f"reason={self.reason}",
        ]
        if self.weekly_required is not None:
            parts.append(f"weekly={self.weekly_count}/{self.weekly_required}")
        for key, value in self.extra.items():
            parts.append(f"{key}={value}")
        if self.detail:
            parts.append(f"detail={self.detail!r}")
        return " ".join(parts)

    def as_record(self) -> dict[str, object]:
        """Render the durable JSON object written to the trail."""
        record: dict[str, object] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "locked": self.locked,
            "reason": self.reason,
        }
        if self.detail:
            record["detail"] = self.detail
        if self.weekly_required is not None:
            record["weekly_count"] = self.weekly_count
            record["weekly_required"] = self.weekly_required
        record.update(self.extra)
        return record


def record_decision(decision: LockDecision, *, log_file: Path | None = None) -> None:
    """Log ``decision`` to the journal and append it to the durable trail.

    Never raises: a failure to *record* why the locker acted must not stop the
    locker from acting. A write failure is reported at ``warning`` rather than
    swallowed, so the recording gap is itself visible.
    """
    line = decision.as_line()
    # Not-enforcing is the state that hid the outage, so it is the state that
    # gets the louder level. An enforced lock is self-evident on screen.
    if decision.locked:
        _logger.info("%s", line)
    else:
        _logger.warning("%s", line)

    append_record(decision.as_record(), log_file=log_file)


def record_no_decision(mode: str, *, log_file: Path | None = None) -> None:
    """Note that a run finished WITHOUT evaluating the lock at all.

    ``--sync-only`` and ``--status`` never reach the decision ladder. Recording
    that explicitly is what keeps the trail honest: during the outage the
    journal was full of healthy 15-minute sync runs, which made the system look
    alive while no enforcement decision had been made for days. "This run did
    not decide" and "this run decided not to lock" must never look alike.

    Written at ``info`` because these modes run constantly and are expected;
    the durable trail is what makes them auditable, not the log level.
    """
    # What the LOCKER was doing at this moment rides along. systemd cannot
    # start a second instance of an already-active Type=simple unit, so on
    # 2026-08-30 the 09:30-14:00 timer triggers were silent no-ops and the
    # only records in that window were these sync lines -- which said nothing
    # about the run that had decided to lock at 09:01 and was still waiting.
    # This is the every-15-minutes heartbeat that already exists, so putting
    # the observation here needs no new unit in the enforcement path.
    locker = locker_unit_active()
    waiting = read_queue_wait()
    _logger.info(
        "DECISION lock=n/a reason=mode_makes_no_decision mode=%s "
        "locker_running=%s%s — this mode never evaluates the lock",
        mode,
        "unknown" if locker is None else locker,
        (
            f" queued_behind={','.join(waiting.get('blocked_by', []))}"
            if waiting
            else ""
        ),
    )
    record: dict[str, object] = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "locked": None,
        "reason": "mode_makes_no_decision",
        "mode": mode,
        "locker_running": locker,
    }
    if waiting:
        record["queued_behind"] = waiting.get("blocked_by", [])
    append_record(record, log_file=log_file)


def record_run_aborted(
    reason: str, detail: str, *, log_file: Path | None = None
) -> None:
    """Note that a run could not reach the decision ladder at all.

    Distinct from :func:`record_no_decision`, which covers modes that are
    *designed* never to decide. This covers a run that meant to decide and
    could not -- the case that produced the 2026-08-30 restart loop, where
    1695 runs died before recording anything and the only evidence was a
    stack trace in the journal.

    Written at ``warning``: unlike the sync modes, this is never expected.

    Args:
        reason: Machine-readable slug for the trail.
        detail: One human sentence about what was missing.
        log_file: Override for the trail path (for testing).
    """
    _logger.warning(
        "DECISION lock=n/a reason=%s — %s",
        reason,
        detail,
    )
    append_record(
        {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "locked": None,
            "reason": reason,
            "detail": detail,
        },
        log_file=log_file,
    )


def read_decisions(*, log_file: Path | None = None) -> list[dict[str, object]]:
    """Return the recorded decisions, oldest first.

    Corrupt lines are skipped with a warning rather than aborting the read: a
    partially damaged trail is still worth far more than no trail.
    """
    target = DECISION_LOG_FILE if log_file is None else log_file
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Genuinely benign and expected before the first run ever records a
        # decision, but still said out loud: "no history" and "history I could
        # not read" must never look the same to whoever is investigating.
        _logger.warning(
            "No decision log at %s yet — no lock decision has been recorded "
            "on this machine (this is normal before the first locker run)",
            target,
        )
        return []
    except OSError as exc:
        _logger.warning("Could not read the decision log at %s (%s)", target, exc)
        return []

    records: list[dict[str, object]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            _logger.warning("Skipping a corrupt decision-log line (%s)", exc)
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
        else:
            _logger.warning("Skipping a decision-log line that is not an object")
    return records
