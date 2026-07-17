#!/usr/bin/env python3
"""Pre-commit hook: fail if any file exceeds MAX_LINES lines."""

import logging
import sys

MAX_LINES = 400

_logger = logging.getLogger(__name__)


def main() -> int:
    """Return 1 if any file exceeds the line limit, else 0."""
    failed = False
    for filepath in sys.argv[1:]:
        try:
            with open(filepath, encoding="utf-8", errors="replace") as fh:
                count = sum(1 for _ in fh)
        except OSError as exc:
            _logger.warning(
                "Could not read %s to count its lines (%s) — failing the check "
                "rather than assuming the file is within the %d-line limit",
                filepath,
                exc,
                MAX_LINES,
            )
            failed = True
            continue
        if count > MAX_LINES:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
