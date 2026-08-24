"""A backend that answers with stale data must still be called broken.

The 2026-08-24 lockout had two causes and only one of them raised. These
tests cover the silent one: the GitHub mirror answered every request
correctly while the phone had stopped writing to it nine days earlier.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from screen_locker import _sync_client
from screen_locker._source_health import (
    SourceFinding,
    collect_source_findings,
    describe_staleness,
    explain_findings,
)

_NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


class TestCollectSourceFindings:
    """The healthy machine must produce no findings at all.

    An always-on warning is one nobody reads. If a fresh, working sync still
    printed "this may be wrong", the panel added for 2026-08-24 would become
    background noise and stop carrying information.
    """

    def test_healthy_and_fresh_reports_nothing(self) -> None:
        """No dead backend and recent data means silence."""
        _sync_client.clear_degraded_sources()

        findings = collect_source_findings(
            newest_synced=_NOW - timedelta(hours=3), now=_NOW
        )

        assert findings == []


class TestDescribeStaleness:
    """Turning "answered fine, but the data is old" into a stated fault."""

    def test_fresh_source_is_not_a_finding(self) -> None:
        """Today's data must not raise an alarm."""
        newest = _NOW - timedelta(hours=3)

        assert describe_staleness("GitHub mirror", newest, now=_NOW) is None

    def test_nine_day_silence_is_reported_with_its_age(self) -> None:
        """The real 2026-08-15 mirror silence, named in days."""
        newest = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)

        finding = describe_staleness("GitHub mirror", newest, now=_NOW)

        assert finding is not None
        assert "8 days" in finding.headline
        assert "2026-08-15" in finding.detail

    def test_boundary_is_not_flagged(self) -> None:
        """Just inside the window stays quiet, so rest days do not cry wolf."""
        newest = _NOW - timedelta(days=1, hours=23)

        assert describe_staleness("GitHub mirror", newest, now=_NOW) is None

    def test_empty_backend_is_its_own_finding(self) -> None:
        """ "Answered with nothing" is different from "answered with old"."""
        finding = describe_staleness("Firebase", None, now=_NOW)

        assert finding is not None
        assert "no workouts at all" in finding.headline


class TestExplainFindings:
    """The text a locked-out user actually reads."""

    def test_no_findings_render_nothing(self) -> None:
        """A healthy machine must not show a diagnostics block."""
        assert explain_findings([]) == ""

    def test_findings_name_the_backend_and_the_consequence(self) -> None:
        """The panel must say it is a sync fault, not a missed workout."""
        text = explain_findings(
            [SourceFinding("Firebase", "Firebase is unreadable", "HTTP 400.")]
        )

        assert "Firebase is unreadable" in text
        assert "sync fault, not a missed workout" in text
