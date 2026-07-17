"""The status window's "Check Phone" verify-and-credit flow.

Split out of ``status_view`` to keep that module focused on rendering. Holds
the one place the voluntary status window *writes*: a verified workout here is
appended to the log and earns its shutdown reward, exactly as the locked
screen's unlock does.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # pylint: disable=no-name-in-module
from typing import TYPE_CHECKING

from screen_locker._status_data import gather_status

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future
    from pathlib import Path

    from screen_locker._workout_credit import WorkoutCreditResult
    from screen_locker.screen_lock import ScreenLocker


def _make_bare_verifier(log_file: Path) -> ScreenLocker:
    """Build a minimal ``ScreenLocker`` for verification calls.

    Same ``object.__new__`` bypass ``screen_lock.py`` already uses for
    ``--status`` — just enough state for the verification mixins' methods
    to run, no Tk lock UI, no ``__init__`` side effects.
    """
    from screen_locker.screen_lock import ScreenLocker

    verifier = object.__new__(ScreenLocker)
    verifier.log_file = log_file
    verifier.workout_data = {}
    return verifier


def _verify_phone_then_runnerup(
    verifier: ScreenLocker,
) -> tuple[str | None, str, str, str | None]:
    """Check StrongLifts first, then RunnerUp as a fallback (worker-thread safe).

    Mirrors the locked screen's StrongLifts→RunnerUp chain (``_ui_flows.py``):
    a user may have run instead of lifted, so a failed phone check falls back
    to today's RunnerUp export. Only calls the verifier's ADB methods — never
    touches Tk — so it is safe to run inside a background thread.

    Returns ``(credited_type, status, phone_message, runnerup_message)`` where
    ``credited_type`` is ``"phone_verified"`` / ``"runnerup_verified"`` on a
    verified workout, or ``None`` when neither source verified.
    ``runnerup_message`` is ``None`` when StrongLifts verified and RunnerUp was
    never consulted.
    """
    phone_status, phone_message = verifier._verify_phone_workout()
    if phone_status == "verified":
        return "phone_verified", phone_status, phone_message, None
    runnerup_status, runnerup_message = verifier._verify_runnerup_workout()
    if runnerup_status == "verified":
        return "runnerup_verified", runnerup_status, phone_message, runnerup_message
    return None, runnerup_status, phone_message, runnerup_message


class PhoneCheckMixin:
    """The "Check Phone" button: verify today's workout, then credit it.

    Composed onto ``StatusWindow``, which supplies ``log_file``,
    ``verifier_factory``, ``root``, ``render`` and the result/message slots
    declared below.
    """

    log_file: Path
    verifier_factory: Callable[[Path], ScreenLocker]
    _phone_future: Future[tuple[str | None, str, str, str | None]] | None
    _phone_check_result: tuple[str, str] | None
    _credit_message: str | None

    def _on_check_phone_clicked(self) -> None:
        """Verify today's workout (StrongLifts then RunnerUp) and apply its reward.

        Runs the two-step check in one background worker so the Tk loop stays
        responsive, then polls the future. Unlike the old display-only probe,
        a verified result here writes the entry and applies the shutdown bonus
        (see :meth:`_on_phone_check_result`).
        """
        self._phone_check_result = None
        self._credit_message = None
        verifier = self.verifier_factory(self.log_file)
        executor = ThreadPoolExecutor(max_workers=1)
        self._phone_future = executor.submit(_verify_phone_then_runnerup, verifier)
        executor.shutdown(wait=False)
        self._poll_phone_check()

    def _poll_phone_check(self) -> None:
        """Poll the background verification future until it resolves."""
        if self._phone_future is not None and self._phone_future.done():
            self._on_phone_check_result(*self._phone_future.result())
        else:
            self.root.after(500, self._poll_phone_check)

    def _on_phone_check_result(
        self,
        credited_type: str | None,
        status: str,
        phone_message: str,
        runnerup_message: str | None,
    ) -> None:
        """Apply credit on a verified workout, else show a combined failure.

        On a verified result this writes the entry and applies the reward via
        ``_apply_workout_credit`` — the same path the locked screen's
        ``unlock_screen`` and the "Log Manual Workout" button use, guarded
        against double-crediting on the same day. When neither source verified,
        it shows both messages so the user knows why nothing counted.
        """
        if credited_type is not None:
            message = (
                runnerup_message
                if credited_type == "runnerup_verified"
                else phone_message
            )
            source_label = (
                "RunnerUp" if credited_type == "runnerup_verified" else "StrongLifts"
            )
            verifier = self.verifier_factory(self.log_file)
            verifier.workout_data = {"type": credited_type, "source": message or ""}
            credit = verifier._apply_workout_credit()
            self._credit_message = "\n".join(
                self._credit_result_lines(f"{source_label} verified: {message}", credit)
            )
        else:
            self._phone_check_result = (
                status,
                f"StrongLifts: {phone_message} · RunnerUp: {runnerup_message}",
            )
        self.render(gather_status())

    def _credit_result_lines(
        self, header: str, credit: WorkoutCreditResult
    ) -> list[str]:
        """Human-readable outcome lines for an applied workout credit.

        Shared by the "Check Phone" verify path and the "Log Manual Workout"
        path so both report the reward identically: the base +2h shutdown push
        for the day's first workout, the +1h bonus for an additional same-day
        verified workout, and any debt cleared — or a note when this exact
        workout was already recorded today (idempotent, no new credit).
        """
        lines = [header]
        if credit.already_counted_today:
            lines.append("(Already recorded today — no additional credit.)")
            return lines
        if credit.shutdown_adjusted:
            lines.append("Shutdown time +2h later!")
        if credit.extra_bonus_delta > 0:
            lines.append(f"Extra workout today! +{credit.extra_bonus_delta}h tonight")
        if credit.new_debt is not None:
            lines.append(f"Workout debt: {credit.new_debt}")
        return lines
