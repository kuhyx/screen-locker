"""Why a workout source is untrustworthy, in words a human can act on.

Two different failures produced the same blank screen on 2026-08-24:

* Firebase raised -- the credential no longer authenticated. Loud, but only
  in the journal.
* The GitHub mirror did *not* raise. It answered promptly and completely with
  data that had stopped changing on 2026-08-15, because the phone had quietly
  stopped writing to it. Nothing in the code compared a record's age to now,
  so a backend that had been dead for nine days looked identical to a backend
  reporting "no workouts yet today".

The second is the dangerous one: an exception at least leaves a traceback. A
silent staleness leaves a confident, wrong answer. Both are surfaced here as
the same kind of finding, so the lock screen can explain itself instead of
accusing the user of skipping a workout they actually did.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from screen_locker._degraded_sources import degraded_sources

# A phone that has synced nothing for this long is not "quiet", it is broken.
# Two days spans a rest day plus a travel day without crying wolf, while still
# catching the nine-day silence that made 2026-08-24 unexplainable.
STALE_AFTER = timedelta(days=2)


@dataclass(frozen=True)
class SourceFinding:
    """One reason a workout source cannot be trusted right now."""

    name: str
    headline: str
    detail: str


def describe_staleness(
    name: str, newest: datetime | None, *, now: datetime | None = None
) -> SourceFinding | None:
    """Return a finding when *name*'s newest record is too old, else None.

    Args:
        name: The backend, as the user would name it ("GitHub mirror").
        newest: Timestamp of the most recent record it returned, or None when
            it returned nothing at all.
        now: Injected for tests.
    """
    instant = now if now is not None else datetime.now(tz=timezone.utc)
    if newest is None:
        return SourceFinding(
            name=name,
            headline=f"{name} returned no workouts at all",
            detail=(
                f"{name} answered, but with an empty log. Either nothing has "
                "ever synced from your phone, or this backend is not the one "
                "your phone writes to."
            ),
        )
    age = instant - newest.astimezone(timezone.utc)
    if age < STALE_AFTER:
        return None
    return SourceFinding(
        name=name,
        headline=f"{name} has not changed in {age.days} days",
        detail=(
            f"The newest workout {name} knows about is from "
            f"{newest.date().isoformat()} — {age.days} days ago. It is "
            "answering, so nothing looks broken, but your phone has stopped "
            "writing to it. A workout logged today would not appear here."
        ),
    )


def collect_source_findings(
    *, newest_synced: datetime | None = None, now: datetime | None = None
) -> list[SourceFinding]:
    """Gather every reason the workout sources may be lying right now.

    Combines the two failure shapes: backends that raised (recorded by
    ``_sync_client``) and backends that answered with stale data.
    """
    findings = [
        SourceFinding(
            name=source.name,
            headline=f"{source.name} could not be read at all",
            detail=(
                f"{source.name} refused the connection: {source.reason}. Your "
                "phone syncs workouts there, so anything logged today is "
                "invisible to this machine until that is fixed."
            ),
        )
        for source in degraded_sources()
    ]
    stale = describe_staleness("the workout sync", newest_synced, now=now)
    if stale is not None:
        findings.append(stale)
    return findings


def explain_findings(findings: list[SourceFinding]) -> str:
    """Render findings as the block of text shown on the lock screen.

    Deliberately plain prose: this is read by someone who just finished a
    two-hour workout and is being told it does not count. "Sync error" is
    not an explanation; naming the backend, the age and the consequence is.
    """
    if not findings:
        return ""
    lines = ["Why this may be wrong:"]
    lines.extend(f"• {finding.headline}\n  {finding.detail}" for finding in findings)
    lines.append(
        "If you did work out, this is a sync fault, not a missed workout — "
        "use TRY AGAIN, or log it once sync is restored."
    )
    return "\n".join(lines)
