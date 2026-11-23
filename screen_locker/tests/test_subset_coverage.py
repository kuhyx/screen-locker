"""A ``-k`` run is a subset: the 100% coverage bar is for whole-suite runs.

The board's done_checks are ``pytest -q -k <name>``; with ``fail_under = 100``
in pyproject every one of them exited 1 on green tests (2026-11-23).
"""

from __future__ import annotations

from types import SimpleNamespace

from screen_locker.tests import _subset_coverage


def _config(keyword: str, fail_under: float | None) -> SimpleNamespace:
    cov = SimpleNamespace(options=SimpleNamespace(cov_fail_under=fail_under))
    manager = SimpleNamespace(getplugin=lambda name: cov if name == "_cov" else None)
    return SimpleNamespace(
        option=SimpleNamespace(keyword=keyword), pluginmanager=manager
    )


def test_keyword_run_drops_the_coverage_bar() -> None:
    """``-k name`` selects a subset: its coverage is not held to fail_under."""
    config = _config("preview_review_sequence", 100)
    _subset_coverage.pytest_sessionstart(SimpleNamespace(config=config))
    assert config.pluginmanager.getplugin("_cov").options.cov_fail_under is None


def test_whole_suite_keeps_the_coverage_bar() -> None:
    """No ``-k``: the commit gate's full run still needs 100%."""
    config = _config("", 100)
    _subset_coverage.pytest_sessionstart(SimpleNamespace(config=config))
    assert config.pluginmanager.getplugin("_cov").options.cov_fail_under == 100


def test_no_coverage_plugin_is_left_alone() -> None:
    """``--no-cov`` or ``-p no:cov``: nothing to relax, no crash."""
    manager = SimpleNamespace(getplugin=lambda _name: None)
    config = SimpleNamespace(option=SimpleNamespace(keyword="x"), pluginmanager=manager)
    _subset_coverage.pytest_sessionstart(SimpleNamespace(config=config))
