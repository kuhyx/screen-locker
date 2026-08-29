"""Tests for _shutdown_base module (daily shutdown base reset)."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from screen_locker._shutdown_base import get_base_hours, reset_to_base_if_new_day

if TYPE_CHECKING:
    from pathlib import Path


class TestGetBaseHours:
    """Tests for get_base_hours."""

    def test_returns_defaults_when_file_missing(self, tmp_path: Path) -> None:
        """Missing file → (21, 21) without errors (lines 29-30)."""
        assert get_base_hours(tmp_path / "nonexistent.json") == (21, 21)

    def test_returns_stored_hours(self, tmp_path: Path) -> None:
        """Valid file with custom hours → exact values (lines 31-37)."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"base_mon_wed_hour": 22, "base_thu_sun_hour": 20}))
        assert get_base_hours(f) == (22, 20)

    def test_returns_defaults_on_corrupt_json(self, tmp_path: Path) -> None:
        """Corrupt JSON → (21, 21) via except (lines 38-39)."""
        f = tmp_path / "state.json"
        f.write_text("not-json")
        assert get_base_hours(f) == (21, 21)

    def test_returns_defaults_on_oserror(self) -> None:
        """OSError on open → (21, 21) via except (lines 38-39)."""
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.open.side_effect = OSError("read fail")
        assert get_base_hours(mock_path) == (21, 21)

    def test_uses_default_when_key_missing(self, tmp_path: Path) -> None:
        """Keys absent in JSON → each defaults to 21."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({}))
        assert get_base_hours(f) == (21, 21)


class TestResetToBaseIfNewDay:
    """Tests for reset_to_base_if_new_day."""

    def _make_mixin(self, write_ok: bool = True) -> MagicMock:
        """Build a minimal mixin mock."""
        mixin = MagicMock()
        mixin._read_shutdown_config.return_value = (21, 21, 5)
        mixin._write_shutdown_config.return_value = write_ok
        return mixin

    def test_returns_false_when_already_reset_today(self, tmp_path: Path) -> None:
        """Same-day last_reset_date → early False return (line 63)."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_reset_date": today}))
        assert reset_to_base_if_new_day(f, self._make_mixin()) is False

    def test_resets_when_new_day(self, tmp_path: Path) -> None:
        """Different last_reset_date → reset performed, returns True (lines 67-100)."""
        f = tmp_path / "state.json"
        f.write_text(
            json.dumps(
                {
                    "last_reset_date": "2000-01-01",
                    "base_mon_wed_hour": 21,
                    "base_thu_sun_hour": 21,
                }
            )
        )
        mixin = self._make_mixin()
        assert reset_to_base_if_new_day(f, mixin) is True
        mixin._write_shutdown_config.assert_called_once_with(21, 21, 5, restore=True)

    def test_resets_when_no_state_file(self, tmp_path: Path) -> None:
        """No state file → treated as new day, reset performed (lines 67-100)."""
        f = tmp_path / "nonexistent.json"
        mixin = self._make_mixin()
        assert reset_to_base_if_new_day(f, mixin) is True
        mixin._write_shutdown_config.assert_called_once()

    def test_returns_false_when_write_config_fails(self, tmp_path: Path) -> None:
        """_write_shutdown_config returns False → reset fails (lines 74-76)."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_reset_date": "2000-01-01"}))
        mixin = self._make_mixin(write_ok=False)
        assert reset_to_base_if_new_day(f, mixin) is False

    def test_uses_default_morning_end_when_config_is_none(self, tmp_path: Path) -> None:
        """_read_shutdown_config returns None → morning_end defaults to 5 (line 71 else)."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_reset_date": "2000-01-01"}))
        mixin = MagicMock()
        mixin._read_shutdown_config.return_value = None
        mixin._write_shutdown_config.return_value = True
        reset_to_base_if_new_day(f, mixin)
        mixin._write_shutdown_config.assert_called_once_with(21, 21, 5, restore=True)

    def test_clears_sick_day_state_file_on_reset(self, tmp_path: Path) -> None:
        """Existing sick-day file is deleted during reset (lines 79-82)."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_reset_date": "2000-01-01"}))
        sick_file = tmp_path / "sick.json"
        sick_file.write_text("{}")
        mixin = self._make_mixin()
        assert reset_to_base_if_new_day(f, mixin, sick_day_state_file=sick_file) is True
        assert not sick_file.exists()

    def test_handles_oserror_on_sick_file_unlink(self, tmp_path: Path) -> None:
        """OSError when removing sick-day file is logged but reset still returns True (lines 83-86)."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_reset_date": "2000-01-01"}))
        sick_mock = MagicMock()
        sick_mock.exists.return_value = True
        sick_mock.unlink.side_effect = OSError("busy")
        mixin = self._make_mixin()
        assert reset_to_base_if_new_day(f, mixin, sick_day_state_file=sick_mock) is True

    def test_handles_corrupt_state_file_gracefully(self, tmp_path: Path) -> None:
        """Corrupt state file treated as no date → reset runs (lines 64-65 except branch)."""
        f = tmp_path / "state.json"
        f.write_text("not-json")
        mixin = self._make_mixin()
        assert reset_to_base_if_new_day(f, mixin) is True

    def test_handles_oserror_on_state_write(self, tmp_path: Path) -> None:
        """OSError writing the new state file is caught; function still returns True (lines 96-97)."""
        # Use a mock path that fails only on "w" opens.
        state_mock = MagicMock()
        state_mock.exists.return_value = False  # triggers fresh-reset path
        state_mock.open.side_effect = OSError("disk full")
        mixin = self._make_mixin()
        # _write_shutdown_config succeeds, so True is returned even if state write fails.
        assert reset_to_base_if_new_day(state_mock, mixin) is True

    def test_sick_day_state_file_not_deleted_when_absent(self, tmp_path: Path) -> None:
        """No sick-day file passed → branch skipped, no AttributeError (line 79 branch False)."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_reset_date": "2000-01-01"}))
        mixin = self._make_mixin()
        assert reset_to_base_if_new_day(f, mixin, sick_day_state_file=None) is True

    def test_sick_day_file_not_deleted_when_it_doesnt_exist(
        self, tmp_path: Path
    ) -> None:
        """sick_day_state_file passed but doesn't exist → .unlink() not called (line 79 .exists() False)."""
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"last_reset_date": "2000-01-01"}))
        sick_file = tmp_path / "nonexistent_sick.json"
        mixin = self._make_mixin()
        assert reset_to_base_if_new_day(f, mixin, sick_day_state_file=sick_file) is True
        assert not sick_file.exists()
