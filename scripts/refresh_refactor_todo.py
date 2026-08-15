#!/usr/bin/env python3
"""Regenerate the violations table in ``refactor_claude_todo.md``.

The todo file doubles as the prompt for the next refactor session, so its
counts must never go stale: a hand-written hand-off summary drifts the moment
one more file is split. This script derives everything from the gate's own
output plus ``git log`` churn, so the resume state is simply "run this, then
take the top N".

ROI = lines x commits in the last year. A long file nobody edits has near-zero
payoff and should not be first.

Usage:
    python3 scripts/refresh_refactor_todo.py [--check]

``--check`` exits 1 if the file is out of date instead of rewriting it, so CI
or a hook can fail on a stale table.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import re
import shutil
import subprocess

_logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
TODO_FILE = REPO_ROOT / "refactor_claude_todo.md"
GATE = REPO_ROOT / "scripts" / "check_file_length.sh"
FALLBACK_GATE = Path.home() / "utils" / "scripts" / "check_file_length.sh"

BEGIN_MARKER = "<!-- BEGIN GENERATED VIOLATIONS -->"
END_MARKER = "<!-- END GENERATED VIOLATIONS -->"
TOP_N = 15

_VIOLATION_RE = re.compile(
    r"^\s*(?P<path>.+?):\s*(?P<lines>\d+) lines \(over by \d+\)$"
)


def _executable(name: str) -> str:
    """Absolute path to `name`, so the subprocess call is not PATH-dependent."""
    found = shutil.which(name)
    if found is None:
        msg = f"required executable not found on PATH: {name}"
        raise FileNotFoundError(msg)
    return found


def gate_script() -> Path:
    """The file-length gate to run, preferring the in-repo vendored copy."""
    return GATE if GATE.is_file() else FALLBACK_GATE


def collect_violations() -> list[tuple[Path, int]]:
    """Every file over the cap, as (repo-relative path, line count)."""
    script = gate_script()
    if not script.is_file():
        msg = f"file-length gate not found at {script}"
        raise FileNotFoundError(msg)
    result = subprocess.run(
        [_executable("bash"), str(script), "--all"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # Exit 0 means no violations; 1 means violations were listed on stderr.
    # Anything else is a real failure and must not be reported as "all clean".
    if result.returncode not in (0, 1):
        msg = (
            f"file-length gate failed with exit {result.returncode}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
        raise RuntimeError(msg)

    violations: list[tuple[Path, int]] = []
    for line in (result.stderr + result.stdout).splitlines():
        match = _VIOLATION_RE.match(line)
        if match is None:
            continue
        path = Path(match.group("path"))
        try:
            relative = path.relative_to(REPO_ROOT)
        except ValueError:
            # The gate reported a file outside the repo root. Keep it in the
            # table (it is still a violation) but say so, because an absolute
            # path in the output means the gate was run from the wrong cwd.
            _logger.warning(
                "gate reported %s outside the repo root %s — listing it with "
                "its absolute path; check the cwd the gate ran in",
                path,
                REPO_ROOT,
            )
            relative = path
        violations.append((relative, int(match.group("lines"))))
    return violations


def commits_last_year(path: Path) -> int:
    """How many commits touched `path` in the last year (0 if untracked)."""
    result = subprocess.run(
        [_executable("git"), "log", "--since=1 year ago", "--oneline", "--", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _logger.warning(
            "git log failed for %s (%s) — counting 0 commits, so its ROI "
            "rank will read lower than it should",
            path,
            result.stderr.strip(),
        )
        return 0
    return len(result.stdout.splitlines())


def kind_of(path: Path) -> str:
    """Coarse bucket used in the table's ``kind`` column."""
    if path.suffix in {".md", ".txt", ".rst", ".tex"}:
        return "prose"
    return "code"


def render_table(rows: list[tuple[int, int, int, Path]]) -> str:
    """The markdown section between the generated-content markers."""
    total_files = len(rows)
    total_over = sum(lines - 250 for _, lines, _, _ in rows)
    longest = max((lines for _, lines, _, _ in rows), default=0)

    out = [BEGIN_MARKER, ""]
    if not rows:
        out += [
            "**No violations.** Every file is at or under the 250-line cap.",
            "",
            END_MARKER,
        ]
        return "\n".join(out)

    out += [
        f"- **{total_files} files** currently exceed 250 lines.",
        f"- **{total_over:,} lines** over the cap in total (the work left to "
        f"do); longest file is **{longest}** lines.",
        "",
        "ROI = lines x commits in the last year. Work top-down; a long file "
        "nobody edits",
        "has near-zero payoff and should not be first.",
        "",
        "| lines | commits/yr | kind | file |",
        "| ----: | ---------: | :--- | :--- |",
    ]
    for _, lines, commits, path in rows[:TOP_N]:
        out.append(f"| {lines} | {commits} | {kind_of(path)} | `{path}` |")

    remaining = total_files - min(TOP_N, total_files)
    if remaining > 0:
        out += [
            "",
            f"_({remaining} further files over 250 lines not listed — "
            "re-run `python3 scripts/refresh_refactor_todo.py` for the "
            "current set.)_",
        ]
    out += ["", END_MARKER]
    return "\n".join(out)


def build_section() -> str:
    """Compute ROI for every violation and render the table."""
    rows = []
    for path, lines in collect_violations():
        # One git log per file, not two: this runs over ~70 files.
        commits = commits_last_year(path)
        rows.append((lines * commits, lines, commits, path))
    rows.sort(key=lambda row: (-row[0], -row[1]))
    return render_table(rows)


def splice(original: str, section: str) -> str:
    """Replace the marked region of `original` with `section`."""
    start = original.find(BEGIN_MARKER)
    end = original.find(END_MARKER)
    if start == -1 or end == -1:
        msg = (
            f"{TODO_FILE.name} is missing the generated-content markers "
            f"({BEGIN_MARKER} / {END_MARKER})"
        )
        raise ValueError(msg)
    return original[:start] + section + original[end + len(END_MARKER) :]


def main() -> int:
    """Rewrite (or check) the todo file's violations table."""
    parser = argparse.ArgumentParser(description=__doc__)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the table is out of date instead of rewriting it",
    )
    args = parser.parse_args()

    original = TODO_FILE.read_text()
    updated = splice(original, build_section())

    if args.check:
        if updated != original:
            _logger.error(
                "%s is out of date — run `python3 scripts/refresh_refactor_todo.py`",
                TODO_FILE.name,
            )
            return 1
        return 0

    if updated != original:
        TODO_FILE.write_text(updated)
        _logger.info("Updated %s", TODO_FILE.name)
    else:
        _logger.info("%s already up to date", TODO_FILE.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
