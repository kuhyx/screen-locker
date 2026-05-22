"""Tests for scheduled skip date feature in screen_lock.py."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from python_pkg.screen_locker.tests.conftest import create_locker

if TYPE_CHECKING:
    from pathlib import Path

    from python_pkg.screen_locker.screen_lock import ScreenLocker


class TestIsScheduledSkipToday:
    """Tests for ScreenLocker._is_scheduled_skip_today."""

    def _make_locker(self, mock_tk: MagicMock, tmp_path: Path) -> ScreenLocker:
        return create_locker(mock_tk, tmp_path)

    def test_returns_false_when_file_absent(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when scheduled_skips.json does not exist."""
        locker = self._make_locker(mock_tk, tmp_path)
        skip_file = tmp_path / "scheduled_skips.json"
        with patch(
            "python_pkg.screen_locker.screen_lock.SCHEDULED_SKIPS_FILE",
            skip_file,
        ):
            assert locker._is_scheduled_skip_today() is False

    def test_returns_true_when_today_listed(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns True when today's date is in the skips list."""
        locker = self._make_locker(mock_tk, tmp_path)
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        skip_file = tmp_path / "scheduled_skips.json"
        skip_file.write_text(json.dumps([today]))
        with patch(
            "python_pkg.screen_locker.screen_lock.SCHEDULED_SKIPS_FILE",
            skip_file,
        ):
            assert locker._is_scheduled_skip_today() is True

    def test_returns_false_when_today_not_listed(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when today's date is not in the skips list."""
        locker = self._make_locker(mock_tk, tmp_path)
        skip_file = tmp_path / "scheduled_skips.json"
        skip_file.write_text(json.dumps(["1999-01-01", "2000-06-15"]))
        with patch(
            "python_pkg.screen_locker.screen_lock.SCHEDULED_SKIPS_FILE",
            skip_file,
        ):
            assert locker._is_scheduled_skip_today() is False

    def test_returns_false_on_corrupt_json(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when the skips file contains invalid JSON."""
        locker = self._make_locker(mock_tk, tmp_path)
        skip_file = tmp_path / "scheduled_skips.json"
        skip_file.write_text("{not valid json}")
        with patch(
            "python_pkg.screen_locker.screen_lock.SCHEDULED_SKIPS_FILE",
            skip_file,
        ):
            assert locker._is_scheduled_skip_today() is False

    def test_returns_false_on_read_error(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False when the skips file cannot be read (OSError)."""
        locker = self._make_locker(mock_tk, tmp_path)
        skip_file = tmp_path / "scheduled_skips.json"
        skip_file.write_text("[]")
        with (
            patch(
                "python_pkg.screen_locker.screen_lock.SCHEDULED_SKIPS_FILE",
                skip_file,
            ),
            patch("builtins.open", side_effect=OSError("permission denied")),
        ):
            assert locker._is_scheduled_skip_today() is False

    def test_empty_list_returns_false(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Returns False for an empty skips list."""
        locker = self._make_locker(mock_tk, tmp_path)
        skip_file = tmp_path / "scheduled_skips.json"
        skip_file.write_text("[]")
        with patch(
            "python_pkg.screen_locker.screen_lock.SCHEDULED_SKIPS_FILE",
            skip_file,
        ):
            assert locker._is_scheduled_skip_today() is False


class TestScheduledSkipEarlyExit:
    """Tests for _check_non_verify_exits behaviour with scheduled skips."""

    @staticmethod
    def _write_today_skip(tmp_path: Path) -> None:
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        skip_file = tmp_path / "scheduled_skips.json"
        skip_file.write_text(json.dumps([today]))

    def test_exits_on_scheduled_skip_day(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Screen locker calls sys.exit(0) when today is a scheduled skip."""
        self._write_today_skip(tmp_path)
        mock_sys_exit.side_effect = SystemExit(0)

        with pytest.raises(SystemExit):
            create_locker(mock_tk, tmp_path)

        mock_sys_exit.assert_called_once_with(0)

    def test_does_not_exit_when_not_scheduled_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Screen locker proceeds normally when today is not a scheduled skip."""
        # No file written — _is_scheduled_skip_today returns False
        locker = create_locker(mock_tk, tmp_path)

        mock_sys_exit.assert_not_called()
        assert locker is not None

    def test_scheduled_skip_takes_precedence_over_has_logged(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Scheduled skip exits before has_logged or other checks run."""
        self._write_today_skip(tmp_path)
        mock_sys_exit.side_effect = SystemExit(0)

        with pytest.raises(SystemExit):
            create_locker(mock_tk, tmp_path, has_logged=False)

        mock_sys_exit.assert_called_once_with(0)

    def test_verify_only_mode_ignores_scheduled_skip(
        self,
        mock_tk: MagicMock,
        mock_sys_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        """verify_only mode does not consult scheduled skips."""
        self._write_today_skip(tmp_path)

        # verify_only exits because no sick day log, not because of scheduled skip
        create_locker(
            mock_tk,
            tmp_path,
            verify_only=True,
            is_sick_day_log=False,
        )

        mock_sys_exit.assert_called_once_with(0)
