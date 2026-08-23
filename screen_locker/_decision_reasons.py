"""Collect *every* condition that bears on a lock decision, not just the first.

The decision ladders in ``_auto_upgrade`` and ``_startup_checks`` are
first-match-wins: the branch that matches calls ``sys.exit(0)``, so every
later condition is never evaluated and never recorded. That made a line like

    DECISION lock=no reason=early_bird_window_active

ambiguous in the one way that matters: it cannot say whether the workout was
*also* already done. A reader seeing only the early-bird reason cannot tell a
deferred-but-compliant day from a deferred-and-idle one, which is precisely
the question "was it right to skip?" that the decision log exists to answer.

So the acting reason stays exactly as it was -- it is the branch that actually
controlled behaviour, and it stays a stable grep-able slug -- and this module
supplies the *other* conditions that also held, as an ``also=`` extra.

Only side-effect-free predicates belong here. ``_try_auto_upgrade_*`` writes
log entries and does ADB/network work, and ``_save_early_bird_pending`` writes
state; calling any of those to produce a *log line* would turn a reporting
change into a state mutation in the enforcer. Every predicate below is a pure
read.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_logger = logging.getLogger(__name__)

__all__ = ["collect_reasons", "reasons_extra"]


def _holds(slug: str, predicate: Callable[[], bool]) -> bool:
    """Return whether ``predicate`` holds, reporting rather than raising.

    A predicate that fails is reported at ``warning`` and treated as not
    holding: this runs to *annotate* a decision, so a broken annotation must
    never take down the decision itself. Silence would defeat the point --
    a missing reason would otherwise read as a condition that did not hold.
    """
    try:
        return predicate()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _logger.warning(
            "Could not evaluate the '%s' condition while annotating a lock "
            "decision (%s) — it is omitted from this line, so treat its "
            "absence as unknown rather than false",
            slug,
            exc,
        )
        return False


def collect_reasons(predicates: Mapping[str, Callable[[], bool]]) -> list[str]:
    """Return the slugs of every predicate that currently holds."""
    return [slug for slug, pred in predicates.items() if _holds(slug, pred)]


def reasons_extra(
    acting: str, predicates: Mapping[str, Callable[[], bool]]
) -> dict[str, object]:
    """Build the ``also=`` extra for a decision whose acting reason is ``acting``.

    Returns an empty mapping when nothing else applied, so a genuinely
    single-reason decision keeps rendering exactly the line it did before and
    no reader has to learn a new format for the common case.
    """
    others = [slug for slug in collect_reasons(predicates) if slug != acting]
    return {"also": ",".join(others)} if others else {}
