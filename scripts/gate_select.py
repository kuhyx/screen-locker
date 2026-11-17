"""Pick the tests a push must run: only those affected since the last green full run.

Selection is sound, not clever: a Dart test is selected if its transitive
imports reach a changed dart file (lib or test helper); python tests are mapped
by module name as in scripts/test_changed.sh; web runs only when web/ changed.
Anything that can change every test (pubspec, analysis_options, conftest,
pyproject) selects the full suite, and the caller must say so -- selection
never narrows silently.

CLI: gate_select.py BASE [HEAD]   prints JSON of the Selection
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import sys

_HEAD_ARG = 2
_GIT = shutil.which("git") or "git"
_LOG = logging.getLogger(__name__)
APP = "stronglift_replacement/workout_app"
_DIRECTIVE = re.compile(r"^\s*(?:import|export|part)\s[^;]*;", re.MULTILINE)
_QUOTED = re.compile(r"'([^']+)'|\"([^\"]+)\"")
_FULL_DART = (
    f"{APP}/pubspec.yaml",
    f"{APP}/pubspec.lock",
    f"{APP}/analysis_options.yaml",
)
_FULL_PY = {"conftest.py", "pyproject.toml", "pytest.ini", "setup.cfg"}


@dataclass
class Selection:
    """What a push must run, and the reasons (printed by the gate)."""

    dart: list[str] = field(default_factory=list)
    python: list[str] = field(default_factory=list)
    web: bool = False
    full_dart: bool = False
    full_python: bool = False
    why: list[str] = field(default_factory=list)


def _norm(path: str) -> str:
    parts: list[str] = []
    for p in path.split("/"):
        if p == "..":
            parts.pop()
        elif p not in (".", ""):
            parts.append(p)
    return "/".join(parts)


def _imports(root: Path, rel: str, pkg: str) -> set[str]:
    """Repo-relative dart files that `rel` imports, exports or parts."""
    out: set[str] = set()
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _LOG.warning("gate_select: cannot read %s: %s", rel, exc)
        return out
    for stmt in _DIRECTIVE.findall(text):
        for a, b in _QUOTED.findall(stmt):
            uri = a or b
            if uri.startswith(f"package:{pkg}/"):
                cand = f"{APP}/lib/{uri.split('/', 1)[1]}"
            elif ":" in uri:
                continue
            else:
                cand = _norm(f"{Path(rel).parent.as_posix()}/{uri}")
            if (root / cand).is_file():
                out.add(cand)
    return out


def dart_affected_tests(
    root: Path, changed: list[str], pkg: str = "workout_app"
) -> list[str]:
    """Test files whose transitive imports reach a changed dart file."""
    files = sorted(
        p.relative_to(root).as_posix()
        for sub in ("lib", "test")
        for p in (root / APP / sub).rglob("*.dart")
    )
    rev: dict[str, set[str]] = {}
    for f in files:
        for dep in _imports(root, f, pkg):
            rev.setdefault(dep, set()).add(f)
    seen = {c for c in changed if c.endswith(".dart")}
    stack = list(seen)
    while stack:
        for user in rev.get(stack.pop(), ()):
            if user not in seen:
                seen.add(user)
                stack.append(user)
    return sorted(
        f for f in seen if f.startswith(f"{APP}/test/") and f.endswith("_test.dart")
    )


def python_tests_for(changed: list[str], tracked: list[str]) -> tuple[list[str], bool]:
    """(tests, full) for changed python files, mirroring scripts/test_changed.sh."""
    tests: set[str] = set()
    for f in changed:
        if Path(f).name in _FULL_PY:
            return [], True
        if not f.endswith(".py"):
            continue
        base = Path(f).stem.removeprefix("_")
        if base.startswith("test_") or base.endswith("_test"):
            tests.add(f)
            continue
        pat = re.compile(
            rf"(test_{re.escape(base)}|test__{re.escape(base)}|{re.escape(base)}_test)[^/]*\.py$"
        )
        tests.update(t for t in tracked if pat.search(t))
    return sorted(tests), False


def select(root: Path, changed: list[str], tracked: list[str]) -> Selection:
    """Build the selection for a change set."""
    sel = Selection()
    app_changed = [c for c in changed if c.startswith(f"{APP}/")]
    for f in _FULL_DART:
        if f in changed:
            sel.full_dart = True
            sel.why.append(f"{f} changed: the full Dart suite is required")
    helpers = [
        c
        for c in app_changed
        if "/test/" in c and c.endswith(".dart") and not c.endswith("_test.dart")
    ]
    if app_changed and not sel.full_dart:
        sel.dart = dart_affected_tests(root, app_changed)
        extra = (
            f" (incl. {len(helpers)} test helpers, followed by import)"
            if helpers
            else ""
        )
        sel.why.append(
            f"{len(sel.dart)} Dart tests reach {len(app_changed)} changed files{extra}"
        )
    sel.python, sel.full_python = python_tests_for(changed, tracked)
    if sel.full_python:
        sel.why.append("conftest/pyproject changed: the full Python suite is required")
    elif sel.python:
        sel.why.append(
            f"{len(sel.python)} Python test files map to the changed modules"
        )
    sel.web = any(c.startswith("web/") for c in changed)
    if sel.web:
        sel.why.append("web/ changed: vitest coverage runs")
    return sel


def _git(root: Path, *args: str) -> list[str]:
    out = subprocess.run(
        [_GIT, *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str]) -> int:
    """Print the selection for BASE..HEAD as JSON."""
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel")[0])
    logging.basicConfig(level=logging.INFO)
    base, head = argv[1], (argv[_HEAD_ARG] if len(argv) > _HEAD_ARG else "HEAD")
    changed = _git(root, "diff", "--name-only", f"{base}..{head}")
    sel = select(root, changed, _git(root, "ls-files", "*.py"))
    sys.stdout.write(json.dumps(asdict(sel), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
