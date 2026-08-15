#!/usr/bin/env python3
"""Pre-commit hook: ban silent failures in Dart, mirroring the Python hook.

``check_silent_failures.py`` has enforced this rule for Python since the PC's
workout sync silently did nothing for weeks. It is gated on ``types: [python]``,
so it has never looked at a single Dart file — and the workout app is where the
same class of bug is most expensive, because a swallowed sync error there costs
the user a workout with nothing anywhere saying so.

The rule matches the Python hook: every ``catch`` must either rethrow or say
what happened somewhere a human will actually see. In Dart that means

* ``rethrow`` / ``throw`` (the failure is someone else's problem), or
* ``log(...)`` from ``dart:developer`` -- the release-safe channel, and the one
  the sync services already use at ``level: 1000``, or
* ``debugPrint(...)`` -- accepted because this codebase uses it widely for
  operator-facing storage/backup diagnostics, even though it is stripped in
  release builds.

``print()`` does NOT count: it is lint-banned in this repo and vanishes in
release. A bare ``catchError((_) {})`` is the Dart spelling of ``except: pass``
and is always reported.

Deliberately regex/brace based rather than a real Dart parser: the alternative
is making `analyzer` a hook dependency, and the shapes this needs to recognise
are narrow. It errs toward reporting -- an unparsable handler is a finding,
not a skip, exactly like the Python hook's SyntaxError branch.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
import sys

_logger = logging.getLogger(__name__)

# `log` is dart:developer's; `debugPrint` is flutter/foundation's.
#
# `_setSyncStatus` / `ScaffoldMessenger` count as loud on purpose: telling the
# USER "could not start device flow: <reason>" in the UI is the loudest channel
# there is. The rule is "the failure must be visible", not "it must reach a
# log file", and a screen that reports the error is not a silent failure.
_LOUD_CALLS = (
    "log(",
    "debugPrint(",
    "rethrow",
    "throw ",
    "_setSyncStatus(",
    "ScaffoldMessenger",
)

# `} on Foo catch (e) {`, `} catch (e) {`, `} on Foo {`.
#
# The bare `on Foo {` form requires the preceding `}` of the try block: without
# it this also matched `extension StorageServiceBackup on StorageService {`,
# reporting an extension declaration as a swallowed exception.
_CATCH_RE = re.compile(r"\bcatch\s*\(|\}\s*on\s+\w+\s*\{")

# `.catchError((_) {})` and friends -- an empty body is always silent.
_EMPTY_CATCH_ERROR_RE = re.compile(r"\.catchError\(\s*\([^)]*\)\s*(?:=>\s*)?\{\s*\}")


def _strip_noise(source: str) -> str:
    """Blank out comments and string literals so they cannot match as code.

    A comment mentioning ``log(`` would otherwise make a silent handler look
    loud -- the exact false negative that lets the bug back in.
    """
    out: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        two = source[i : i + 2]
        if two == "//":
            end = source.find("\n", i)
            end = n if end == -1 else end
            out.append(" " * (end - i))
            i = end
        elif two == "/*":
            end = source.find("*/", i + 2)
            end = n if end == -1 else end + 2
            # Keep newlines so line numbers stay correct.
            out.append("".join(c if c == "\n" else " " for c in source[i:end]))
            i = end
        elif source[i] in "\"'":
            quote = source[i]
            j = i + 1
            while j < n and source[j] != quote:
                if source[j] == "\\":
                    j += 1
                if source[j : j + 1] == "\n":
                    break
                j += 1
            j = min(j + 1, n)
            out.append("".join(c if c == "\n" else " " for c in source[i:j]))
            i = j
        else:
            out.append(source[i])
            i += 1
    return "".join(out)


def _block_after(source: str, start: int) -> tuple[str, int] | None:
    """Return the ``{...}`` block that follows ``start``, and its end offset."""
    brace = source.find("{", start)
    if brace == -1:
        return None
    depth = 0
    for idx in range(brace, len(source)):
        if source[idx] == "{":
            depth += 1
        elif source[idx] == "}":
            depth -= 1
            if depth == 0:
                return source[brace : idx + 1], idx
    return None


def _handler_hands_error_on(body: str, catch_clause: str) -> bool:
    """Return True if the handler passes the caught error to its caller.

    ``} on GitHubSyncError catch (e) { return e; }`` is not a silent failure:
    the error becomes the function's result, and whoever asked for it decides
    how loud to be. Same for stashing it in state the UI renders
    (``setState(() => _error = '$e')``) or reassigning a variable that is
    logged after the loop. Reporting these would push the codebase toward
    duplicate logging, which is its own kind of noise.
    """
    name = re.search(r"catch\s*\(\s*(\w+)", catch_clause)
    if name is None:
        return False
    var = name.group(1)
    return bool(
        # `return e;`
        re.search(rf"\breturn\s+{var}\b", body)
        # `failure = retryError;` — reassigned for the caller to report.
        or re.search(rf"=\s*{var}\s*[;,)]", body)
        # `setState(() => _error = '$e')` — rendered by the widget.
        or re.search(rf"=\s*'[^']*\$\{{?{var}\b", body)
    )


def _check_source(path: Path, source: str) -> list[str]:
    """Return one message per silently-swallowing catch in ``source``."""
    code = _strip_noise(source)
    problems: list[str] = []

    for match in _EMPTY_CATCH_ERROR_RE.finditer(code):
        line = code.count("\n", 0, match.start()) + 1
        problems.append(
            f"{path}:{line}: .catchError with an empty body swallows the error "
            f"without logging why — log(...) the reason, or rethrow"
        )

    for match in _CATCH_RE.finditer(code):
        block = _block_after(code, match.start())
        if block is None:
            line = code.count("\n", 0, match.start()) + 1
            problems.append(
                f"{path}:{line}: could not find the catch body — reporting it "
                f"rather than skipping, since it cannot be checked"
            )
            continue
        body, _end = block
        # The clause itself (`catch (retryError)`) names the variable; slice it
        # from the match rather than searching the file, which would find the
        # FIRST catch in the file for every handler.
        clause = code[match.start() : code.find("{", match.start()) + 1]
        # Check the RAW body too: `_error = '$e'` hands the error to the UI,
        # but _strip_noise blanks the string literal it lives in, so the
        # stripped body alone cannot see it.
        raw_body = source[match.start() : match.start() + len(body) + 200]
        if _handler_hands_error_on(body, clause) or _handler_hands_error_on(
            raw_body, clause
        ):
            continue
        if not any(token in body for token in _LOUD_CALLS):
            line = code.count("\n", 0, match.start()) + 1
            problems.append(
                f"{path}:{line}: catch swallows the error without logging why "
                f"— rethrow, or log(..., level: 1000) / debugPrint the reason"
            )
    return problems


def main() -> int:
    """Return 1 if any Dart file swallows an error silently, else 0."""
    problems: list[str] = []
    for filename in sys.argv[1:]:
        path = Path(filename)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _logger.warning(
                "Could not read %s (%s) — reporting it as a problem rather "
                "than skipping it, since its handlers cannot be checked",
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
