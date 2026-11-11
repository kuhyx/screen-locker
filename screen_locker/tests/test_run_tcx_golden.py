"""Cross-language golden test: the app's TCX is accepted by the real verifier.

The workout app (Dart, ``lib/services/tcx_codec.dart``) writes the TCX files
the PC credits. Each language's own round trip passes happily while the other
side's parser disagrees, so the Dart twin
(``stronglift_replacement/workout_app/test/services/tcx_golden_fixture_test.dart``)
encodes ``fixtures/run_tcx/golden_tracks.json`` and compares the result byte
for byte with the ``.tcx`` files checked in next to it. This test feeds those
SAME files to the real ``RunnerUpVerificationMixin`` -- date glob, parser,
run validation and walk summing -- and asserts the km / minutes the JSON
promises. Everything runs on a temporary drop directory: nothing here reads
or writes ``~/data/cloud/RunnerUp``.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from unittest.mock import MagicMock, patch

import pytest

from screen_locker._runnerup_verification import RunnerUpVerificationMixin

FIXTURES = Path(__file__).parent / "fixtures" / "run_tcx"
SAMPLE = "RunnerUp_2026-08-12-17-42-11_Running.tcx"
# ``_TCX_SPORT_TO_INT`` code for "Running" in screen_locker/_runnerup_tcx.py.
SPORT_RUNNING = 0


def _golden() -> dict[str, dict[str, object]]:
    return json.loads((FIXTURES / "golden_tracks.json").read_text(encoding="utf-8"))


class Verifier(RunnerUpVerificationMixin):
    """The real mixin with no phone: only the WebDAV drop directory is read."""

    def __init__(self) -> None:
        self.adb = MagicMock(return_value=(False, ""))

    def _has_adb_device(self) -> bool:
        return False

    def _run_adb(self, args: list[str]) -> tuple[bool, str]:
        return self.adb(args)


@pytest.fixture(name="inbox")
def inbox_fixture(tmp_path: Path) -> Path:
    """A temporary WebDAV inbox standing in for ``~/data/cloud/RunnerUp``."""
    inbox = tmp_path / "cloud" / "RunnerUp"
    inbox.mkdir(parents=True)
    return inbox


def _verify(inbox: Path, today: str) -> tuple[str, str] | None:
    """Run the real file-based verification on ``inbox`` as if it were ``today``."""
    with (
        patch("screen_locker._runnerup_verification.RUNNERUP_WEBDAV_DIRS", (inbox,)),
        patch("screen_locker._runnerup_verification.today_str", return_value=today),
    ):
        return Verifier()._verify_runnerup_via_files()


def _drop(inbox: Path, name: str) -> None:
    shutil.copyfile(FIXTURES / name, inbox / name)


class TestGoldenRun:
    """The app's run file passes the PC's run validation unchanged."""

    def test_run_is_verified_with_the_promised_km_and_minutes(
        self, inbox: Path
    ) -> None:
        """Date glob, parser and validation accept the app's run file."""
        spec = _golden()["running"]
        _drop(inbox, str(spec["file"]))
        expect = spec["expect"]
        assert isinstance(expect, dict)
        result = _verify(inbox, "2026-11-09")
        assert result == (
            expect["status"],
            f"Running: {expect['distance_km']} km in {expect['minutes']} min",
        )

    def test_parsed_fields_match_the_json(self, inbox: Path) -> None:
        """The parser reads sport, duration and distance as the app wrote them."""
        spec = _golden()["running"]
        _drop(inbox, str(spec["file"]))
        data = Verifier()._pull_and_parse_tcx(str(inbox / str(spec["file"])))
        assert data is not None
        assert data["sport"] == SPORT_RUNNING
        assert data["walking"] is False
        assert data["duration_seconds"] == spec["total_seconds"]
        assert data["distance_m"] == pytest.approx(float(str(spec["distance_m"])))
        assert data["activity_id"] == str(spec["started_at"])

    def test_the_local_date_in_the_name_is_what_is_globbed(self, inbox: Path) -> None:
        """Another day does not see the file: the stamp is local, the glob is too."""
        spec = _golden()["running"]
        _drop(inbox, str(spec["file"]))
        assert _verify(inbox, "2026-11-10") is None


class TestGoldenWalk:
    """The app's walk file is a walk, and its moving time is what the PC sums."""

    def test_walk_is_verified_with_the_promised_moving_minutes(
        self, inbox: Path
    ) -> None:
        """A walk is summed per day: legs, km and moving minutes as promised."""
        spec = _golden()["walking"]
        _drop(inbox, str(spec["file"]))
        expect = spec["expect"]
        assert isinstance(expect, dict)
        result = _verify(inbox, "2026-11-09")
        assert result == (
            expect["status"],
            (
                f"Walking: {expect['legs']} walk(s), {expect['distance_km']} km, "
                f"{expect['moving_minutes']} min moving"
            ),
        )

    def test_pc_moving_time_equals_the_apps_total_seconds(self, inbox: Path) -> None:
        """Dart's moving-time rule and the PC's ``track_summary`` agree exactly."""
        spec = _golden()["walking"]
        _drop(inbox, str(spec["file"]))
        data = Verifier()._pull_and_parse_tcx(str(inbox / str(spec["file"])))
        assert data is not None
        assert data["walking"] is True
        assert data["moving_seconds"] == pytest.approx(
            float(str(spec["total_seconds"]))
        )
        assert data["activity_id"] == str(spec["started_at"])

    def test_walk_is_marked_by_file_name_as_with_runnerup(self, inbox: Path) -> None:
        """Like RunnerUp, the app writes ``Sport="Other"``; the name says walk."""
        spec = _golden()["walking"]
        name = str(spec["file"])
        body = (FIXTURES / name).read_text(encoding="utf-8")
        assert 'Sport="Other"' in body
        renamed = inbox / "activity.tcx"
        renamed.write_text(body)
        data = Verifier()._pull_and_parse_tcx(str(renamed))
        assert data is not None
        assert data["walking"] is False
        (inbox / name).write_text(body)
        by_name = Verifier()._pull_and_parse_tcx(str(inbox / name))
        assert by_name is not None
        assert by_name["walking"] is True


class TestRunnerUpSample:
    """The trimmed real RunnerUp export parses to the numbers Dart's decoder sees."""

    def test_parser_sums_both_laps(self, inbox: Path) -> None:
        """Same literals as the Dart decoder test: 624 + 626 s, two laps' metres."""
        _drop(inbox, SAMPLE)
        data = Verifier()._pull_and_parse_tcx(str(inbox / SAMPLE))
        assert data is not None
        assert data["sport"] == SPORT_RUNNING
        assert data["walking"] is False
        assert data["duration_seconds"] == 1250
        assert data["distance_m"] == pytest.approx(983.6306 + 980.7304, abs=1e-3)
        assert data["activity_id"] == "2026-08-12T15:42:11Z"
