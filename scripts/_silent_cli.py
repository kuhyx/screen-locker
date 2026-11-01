"""The argv loop shared by the Python and Dart silent-failure hooks.

Both hooks read every file named on the command line, report what their
``check_source`` finds, and fail closed on a file they cannot read. Only the
per-file check differs, so it is the parameter.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_logger = logging.getLogger(__name__)


def run_hook(check_source: Callable[[Path, str], list[str]]) -> int:
    """Return 1 if ``check_source`` flags any file in ``sys.argv``, else 0."""
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
        problems.extend(check_source(path, source))
    for problem in problems:
        sys.stdout.write(f"{problem}\n")
    return 1 if problems else 0
