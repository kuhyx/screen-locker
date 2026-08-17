#!/usr/bin/env python3
"""Pre-commit hook: ban silent failures.

A caught exception that is swallowed (not re-raised) must say WHY in the log,
loudly. Otherwise the failure is invisible: the caller sees a bland ``None`` /
``[]`` / early return and cannot tell "nothing to do" from "it broke". That is
not hypothetical — the PC's workout sync silently did nothing for weeks because
a missing token returned ``[]`` and a real error only logged at ``INFO``.

The rule: every ``except`` handler must either

* re-``raise`` (the failure is someone else's problem), or
* log at ``warning`` / ``error`` / ``exception`` / ``critical`` with the reason.

``debug`` / ``info`` do not count — an invisible log is a silent failure with
extra steps. ruff's ``S110`` only catches ``except: pass``; this catches the
far more common ``except: log.info(...); return []``.

There is deliberately no escape hatch (per-line lint suppressions are banned
repo-wide too): if a failure is truly benign, say so at ``warning`` and move on.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
import sys

_logger = logging.getLogger(__name__)

# Log levels loud enough that a human actually sees the failure.
_LOUD_LOG_METHODS = frozenset({"warning", "error", "exception", "critical"})


def _is_loud_log_call(node: ast.AST) -> bool:
    """Return True if ``node`` is a ``<something>.warning(...)``-style call."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LOUD_LOG_METHODS
    )


def _handler_is_loud(handler: ast.ExceptHandler) -> bool:
    """Return True if the handler re-raises or logs loudly about the failure."""
    return any(
        isinstance(node, ast.Raise) or _is_loud_log_call(node)
        for node in ast.walk(handler)
    )


def _is_silent_exit(node: ast.AST) -> bool:
    """Return True if ``node`` is a bare ``sys.exit(0)`` / ``exit(0)`` call."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    is_exit = (isinstance(func, ast.Attribute) and func.attr == "exit") or (
        isinstance(func, ast.Name) and func.id == "exit"
    )
    if not is_exit or len(node.args) != 1:
        return False
    arg = node.args[0]
    return isinstance(arg, ast.Constant) and arg.value == 0


def _find_silent_exits(tree: ast.AST) -> list[ast.Call]:
    """Return every ``sys.exit(0)`` not preceded by a loud explanation.

    A process that exits 0 has declared success, so nothing downstream will ever
    flag it — which is precisely how the screen locker stopped enforcing for
    thirteen days in 2026-08 while every unit reported ``0/SUCCESS``. Each such
    exit abandons the work the process was started to do, so it must say why at
    a level a human actually sees.

    The check is per-enclosing-block: an exit is considered explained when a
    loud log call or a ``record_decision(...)``-style helper appears in the same
    body. That keeps it cheap and, more importantly, keeps it free of an escape
    hatch -- there is no comment that silences it.
    """
    offenders: dict[int, ast.Call] = {}
    for block in ast.walk(tree):
        for body_attr in ("body", "orelse", "finalbody"):
            statements = getattr(block, body_attr, None)
            if not isinstance(statements, list):
                continue
            for index, statement in enumerate(statements):
                exits = [
                    inner for inner in ast.walk(statement) if _is_silent_exit(inner)
                ]
                if not exits:
                    continue
                # Scope the search to the exit's OWN statement plus the ones
                # directly before it in the same body. Scanning the whole
                # enclosing body was useless: a sibling method's warning() call
                # elsewhere in the class marked every exit "explained", which is
                # how the original _auto_upgrade.py passed this check while
                # containing exactly the bug it is meant to catch.
                scope = [*statements[:index], statement]
                explained = any(
                    _is_loud_log_call(inner) or _is_explaining_call(inner)
                    for candidate in scope
                    for inner in ast.walk(candidate)
                )
                if explained:
                    continue
                for call in exits:
                    offenders.setdefault(call.lineno, call)
    return [call for _, call in sorted(offenders.items())]


# Helpers that record the reason for stopping. Calling one counts as speaking
# up, the same as logging loudly.
_EXPLAINING_CALLS = frozenset(
    {
        "record_decision",
        "record_no_decision",
        "_record_decision",
        "_record_skip",
        "_skip",
    }
)

# Deliberately NOT relaxed to accept `info`. An INFO line beside sys.exit(0)
# is structurally indistinguishable from the bug this check exists to catch --
# the 2026-08 outage looked exactly like `_logger.info(...); sys.exit(0)`. Since
# the AST cannot tell "finished my job" from "abandoned enforcement", the rule
# stays strict and the handful of genuine completion exits record themselves
# through _EXPLAINING_CALLS instead. A check that cannot distinguish must fail
# closed, not open.


def _is_explaining_call(node: ast.AST) -> bool:
    """Return True if ``node`` calls a helper that records why work stopped."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in _EXPLAINING_CALLS
    return isinstance(func, ast.Name) and func.id in _EXPLAINING_CALLS


def _handler_label(handler: ast.ExceptHandler) -> str:
    """Return a readable name for what the handler catches."""
    if handler.type is None:
        return "except:"
    return f"except {ast.unparse(handler.type)}:"


def _check_source(path: Path, source: str) -> list[str]:
    """Return one message per silently-swallowing except handler in ``source``."""
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        _logger.warning(
            "Could not parse %s (%s at line %s) — reporting it as a problem "
            "rather than skipping it, since its handlers cannot be checked",
            path,
            exc.msg,
            exc.lineno,
        )
        return [f"{path}:{exc.lineno}: could not parse ({exc.msg})"]
    problems = [
        f"{path}:{node.lineno}: {_handler_label(node)} swallows the error without "
        f"logging why — re-raise, or log at warning/error/exception/critical"
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and not _handler_is_loud(node)
    ]
    problems.extend(
        f"{path}:{node.lineno}: sys.exit(0) abandons the work this process was "
        f"started for without saying why — log at warning/error, or record the "
        f"reason (see screen_locker._decision_log.record_decision)"
        for node in _find_silent_exits(tree)
    )
    return problems


def main() -> int:
    """Return 1 if any file swallows an exception silently, else 0."""
    problems: list[str] = []
    for filename in sys.argv[1:]:
        path = Path(filename)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _logger.warning(
                "Could not read %s (%s) — reporting it as a problem rather than "
                "skipping it, since its handlers cannot be checked",
                path,
                exc,
            )
            problems.append(f"{path}: could not read ({exc})")
            continue
        problems.extend(_check_source(path, source))
    for problem in problems:
        sys.stdout.write(f"{problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
