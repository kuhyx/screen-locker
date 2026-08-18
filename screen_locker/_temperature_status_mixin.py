"""Live Warsaw-temperature background check mixin for ``StatusWindow``.

Fetches the same reading the real locker's heat-skip check would see
(``_temperature.fetch_current_temp_with_status``), in a background thread,
bounded to ``_temperature.HARD_TIMEOUT_SECONDS`` — display-only, never
writes to ``log.json``. Host class must provide:

- ``self.root`` — the Tk root, for ``root.after`` polling.
- ``self.temperature_fetcher`` — injected fetch callable (tests override it).
- ``self._temp_future`` / ``self._temp_result`` — state slots, initialized
  by the host's ``__init__``.
- ``self._last_snapshot`` — the most recently rendered ``StatusSnapshot``.
- ``self.render(snapshot)`` — full redraw, called after a result resolves.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # pylint: disable=no-name-in-module
from typing import TYPE_CHECKING

from screen_locker._constants import HEAT_SKIP_CITY, HEAT_SKIP_TEMP_THRESHOLD
from screen_locker._temperature import HARD_TIMEOUT_SECONDS

if TYPE_CHECKING:
    import tkinter as tk

    from screen_locker._temperature import TemperatureCheck


class TemperatureStatusMixin:
    """Provides the background Warsaw-temperature fetch/poll/render."""

    def _section_temperature(self, parent: tk.Widget) -> None:
        """Render the live Warsaw temperature.

        The same reading the real locker's heat-skip check would see,
        fetched in the background.
        """
        del parent
        self._label("Warsaw Temperature", role="body", pad="sm")
        result = self._temp_result
        if result is None:
            self._text(
                "Checking Warsaw temperature…", role="caption", color=self._colors.muted
            )
            return
        if result.timed_out:
            self._text(
                f"Warsaw temperature check timed out after ~"
                f"{int(HARD_TIMEOUT_SECONDS)}s — network may be down.",
                role="caption",
                color=self._colors.warning,
            )
            return
        if result.temp_celsius is None:
            self._text(
                "Warsaw temperature check failed (network/API error).",
                role="caption",
                color=self._colors.warning,
            )
            return
        hot = result.temp_celsius >= HEAT_SKIP_TEMP_THRESHOLD
        self._text(
            f"Warsaw: {result.temp_celsius:.0f}°C (heat-skip threshold "
            f"{HEAT_SKIP_TEMP_THRESHOLD}°C)",
            role="caption",
            color=self._colors.warning if hot else self._colors.muted,
        )
        if hot:
            self._text(
                "Would trigger heat-skip today.",
                role="caption",
                color=self._colors.danger,
            )

    def _start_temperature_check(self) -> None:
        """Submit a background Warsaw-temperature fetch and start polling it.

        Unlike ``_on_check_phone_clicked`` (an explicit, opt-in user action),
        this runs on every window open and refresh, so the first poll is
        always deferred through ``root.after`` rather than checked
        synchronously — otherwise a worker thread that happens to finish
        before this call returns would trigger a second, redundant render
        from within the same call stack that hasn't finished the first one.
        """
        executor = ThreadPoolExecutor(max_workers=1)
        self._temp_future = executor.submit(self.temperature_fetcher, HEAT_SKIP_CITY)
        executor.shutdown(wait=False)
        self.root.after(500, self._poll_temperature_check)

    def _poll_temperature_check(self) -> None:
        """Poll the background temperature-check future until it resolves."""
        if self._temp_future is not None and self._temp_future.done():
            self._on_temperature_check_result(self._temp_future.result())
        else:
            self.root.after(500, self._poll_temperature_check)

    def _on_temperature_check_result(self, result: TemperatureCheck) -> None:
        """Store the resolved temperature check and redraw to show it.

        Re-renders the last snapshot already on screen rather than
        re-gathering from disk — the temperature reading is independent of
        on-disk workout state, so there's nothing new to read.
        """
        self._temp_result = result
        self.render(self._last_snapshot)
