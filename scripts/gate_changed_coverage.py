"""100% line bar for CHANGED dart files, from the lcov of the selected tests.

Usage: gate_changed_coverage.py LCOV CHANGED_FILE...
Paths in CHANGED_FILE are repo-relative; only lib/ files of the app count.
A changed lib file missing from the lcov fails (a file no selected test
loads would otherwise score 100% by absence).
"""

from __future__ import annotations

from pathlib import Path
import logging
import sys

_LOG = logging.getLogger(__name__)
APP_LIB = "stronglift_replacement/workout_app/lib/"


def uncovered(lcov: str, wanted: set[str]) -> dict[str, list[int] | None]:
    """Map wanted lib file -> uncovered line numbers (None = absent from lcov)."""
    result: dict[str, list[int] | None] = dict.fromkeys(wanted)
    current: str | None = None
    for line in lcov.splitlines():
        if line.startswith("SF:"):
            current = f"{APP_LIB}{line[3:].removeprefix('lib/')}"
            if current in wanted:
                result[current] = result[current] or []
            else:
                current = None
        elif line.startswith("DA:") and current is not None:
            num, hits = line[3:].split(",")[:2]
            if int(hits) == 0:
                (result[current] or []).append(int(num))
    return result


def main(argv: list[str]) -> int:
    """Exit 1 listing every changed lib file that is not fully covered."""
    wanted = {f for f in argv[2:] if f.startswith(APP_LIB) and f.endswith(".dart")}
    bad = 0
    for path, lines in sorted(
        uncovered(Path(argv[1]).read_text(encoding="utf-8"), wanted).items()
    ):
        if lines is None or lines:
            _LOG.error("changed file below 100%%: %s (uncovered: %s)", path, "absent from lcov" if lines is None else lines)
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="push-gate: %(message)s")
    raise SystemExit(main(sys.argv))
