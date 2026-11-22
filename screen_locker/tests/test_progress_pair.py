"""The pure part: which fraction leads, in integers, capped, never a float."""

from __future__ import annotations

from fractions import Fraction

import pytest

from screen_locker._constants import MIN_RUN_DISTANCE_KM, MIN_WORKOUT_DURATION_MINUTES
from screen_locker._progress_row import progress_pair, progress_row

_METRES = round(MIN_RUN_DISTANCE_KM * 1000)
_SECONDS = MIN_WORKOUT_DURATION_MINUTES * 60


class TestPair:
    """progress_pair picks the larger fraction and expresses it in integers."""

    def test_distance_leads(self) -> None:
        """1750 m (1/2) beats 300 s (1/6): metres over the metre bar."""
        assert progress_pair(1750.0, 300.0) == (1750, _METRES)

    def test_time_leads(self) -> None:
        """1200 s (2/3) beats 1500 m: seconds over the second bar."""
        assert progress_pair(1500.0, 1200.0) == (1200, _SECONDS)

    def test_a_tie_goes_to_distance(self) -> None:
        """Equal fractions are one answer, and it is the distance form."""
        assert progress_pair(_METRES / 2, _SECONDS / 2) == (_METRES // 2, _METRES)

    def test_done_is_floored(self) -> None:
        """Fractions of a metre or second never round up."""
        assert progress_pair(1750.9, 0.0) == (1750, _METRES)
        assert progress_pair(0.0, 599.99) == (599, _SECONDS)

    def test_done_is_capped_at_the_bar(self) -> None:
        """Past the bar is the bar, never beyond."""
        assert progress_pair(9000.0, 10.0) == (_METRES, _METRES)
        assert progress_pair(1.0, 9000.0) == (_SECONDS, _SECONDS)

    def test_nothing_done_is_no_pair(self) -> None:
        """Zero (or less than a whole unit) is no progress."""
        assert progress_pair(0.0, 0.0) is None
        assert progress_pair(0.4, 0.9) is None

    def test_the_pair_is_the_larger_capped_fraction(self) -> None:
        """Over a grid: done<=target and done/target is the max of the two fractions."""
        steps = (0, 1, 499, 1750, 3499, 3500, 9000)
        for metres in steps:
            for seconds in (*steps, 1799, 1800):
                pair = progress_pair(float(metres), float(seconds))
                by_distance = Fraction(min(metres, _METRES), _METRES)
                by_time = Fraction(min(seconds, _SECONDS), _SECONDS)
                if pair is None:
                    assert not max(by_distance, by_time)
                    continue
                done, target = pair
                assert 0 < done <= target
                assert Fraction(done, target) == max(by_distance, by_time)


class TestRow:
    """progress_row is exactly the agreed contract."""

    def test_the_contract(self) -> None:
        """Every key and every string, nothing else."""
        assert progress_row("2026-11-22", 1750, 3500) == {
            "kind": "progress",
            "entry_id": "progress:2026-11-22:1750:3500",
            "day": "2026-11-22",
            "amount": 0,
            "detail": {
                "source": "workout",
                "for_day": "2026-11-22",
                "done": "1750",
                "target": "3500",
            },
        }

    @pytest.mark.parametrize("bad", [(0, 3500), (-1, 3500)])
    def test_nonpositive_done_is_refused(self, bad: tuple[int, int]) -> None:
        """No row for zero done."""
        assert progress_row("2026-11-22", *bad) is None
