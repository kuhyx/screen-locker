"""Tests for the bounded sync retry that covers the boot/resume network race."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from crdt_sync import GitHubSyncError, RepoNotFoundError
import pytest

from screen_locker._sync_retry import with_sync_retry


class TestWithSyncRetry:
    """Tests for :func:`with_sync_retry`."""

    def test_returns_result_without_retrying_on_success(self) -> None:
        """A working call runs exactly once and returns its value."""
        operation = MagicMock(return_value="ok")
        with patch("screen_locker._sync_retry.sleep") as sleep:
            assert with_sync_retry(operation, description="do the thing") == "ok"
        assert operation.call_count == 1
        sleep.assert_not_called()

    def test_recovers_when_a_later_attempt_succeeds(self) -> None:
        """The boot case: the network comes up mid-retry and the sync lands."""
        operation = MagicMock(side_effect=[GitHubSyncError("network error"), "ok"])
        with patch("screen_locker._sync_retry.sleep") as sleep:
            assert with_sync_retry(operation, description="do the thing") == "ok"
        assert operation.call_count == 2
        sleep.assert_called_once_with(2.0)

    def test_gives_up_after_the_attempt_budget(self) -> None:
        """A genuinely offline run stops after the configured attempts."""
        operation = MagicMock(side_effect=GitHubSyncError("network error"))
        with (
            patch("screen_locker._sync_retry.sleep"),
            pytest.raises(GitHubSyncError),
        ):
            with_sync_retry(operation, description="do the thing", attempts=3)
        assert operation.call_count == 3

    def test_backoff_is_exponential(self) -> None:
        """Waits double each time, so ~14s covers DHCP/DNS without dragging."""
        operation = MagicMock(side_effect=GitHubSyncError("network error"))
        with (
            patch("screen_locker._sync_retry.sleep") as sleep,
            pytest.raises(GitHubSyncError),
        ):
            with_sync_retry(
                operation,
                description="do the thing",
                attempts=4,
                delay_seconds=2.0,
            )
        assert [call.args[0] for call in sleep.call_args_list] == [2.0, 4.0, 8.0]

    def test_retries_repo_not_found_too(self) -> None:
        """Permission-shaped errors retry as well — see the module docstring.

        Classifying transient vs permanent would couple us to which exception
        crdt_sync chains where; a few wasted seconds is the cheaper mistake.
        """
        operation = MagicMock(side_effect=RepoNotFoundError("no access"))
        with (
            patch("screen_locker._sync_retry.sleep"),
            pytest.raises(RepoNotFoundError),
        ):
            with_sync_retry(operation, description="do the thing", attempts=2)
        assert operation.call_count == 2

    @pytest.mark.parametrize("attempts", [1, 0, -1])
    def test_never_runs_fewer_than_once(self, attempts: int) -> None:
        """A nonsensical budget still runs the operation exactly once."""
        operation = MagicMock(side_effect=GitHubSyncError("network error"))
        with (
            patch("screen_locker._sync_retry.sleep") as sleep,
            pytest.raises(GitHubSyncError),
        ):
            with_sync_retry(operation, description="do the thing", attempts=attempts)
        assert operation.call_count == 1
        sleep.assert_not_called()

    def test_logs_each_retry_and_the_final_give_up(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Never fails silently: every swallowed attempt says why, at WARNING."""
        operation = MagicMock(side_effect=GitHubSyncError("network error"))
        with (
            patch("screen_locker._sync_retry.sleep"),
            caplog.at_level("WARNING"),
            pytest.raises(GitHubSyncError),
        ):
            with_sync_retry(operation, description="push things", attempts=3)
        assert "attempt 1/3" in caplog.text
        assert "attempt 2/3" in caplog.text
        assert "after 3 attempt(s)" in caplog.text
        assert "giving up" in caplog.text
        assert "push things" in caplog.text
