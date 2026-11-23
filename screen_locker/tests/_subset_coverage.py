"""Hold only whole-suite runs to pyproject's ``fail_under = 100``.

A ``-k`` run selects a handful of tests, so its total coverage is always far
below 100% and pytest-cov turned every green ``pytest -q -k <name>`` (the
board's done_check form) into exit 1. The commit gate, the nightly
``full_gate.sh`` and CI select no keyword, so they keep the bar. Path-selected
partial runs (``test_changed.sh``, ``push_gate.sh``) pass ``--no-cov``
themselves and are untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    """Drop the coverage bar for a ``-k`` keyword-selected run.

    pytest-cov copies ``fail_under`` into its options when coverage starts
    (before this hook) and checks it at the end; ``None`` skips the check.
    """
    config = session.config
    cov = config.pluginmanager.getplugin("_cov")
    if cov is not None and config.option.keyword:
        cov.options.cov_fail_under = None
