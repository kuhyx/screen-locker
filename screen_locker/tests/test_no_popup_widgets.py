"""Guard: no lock-surface UI module may build a popup window.

A Tk popup is a separate override-redirect window that also takes the Tk grab
for itself, so gatelock's recovery tick covers it and disowns it within a
second of opening. ``_manual_workout_dialog._mw_sport_row`` has the mechanism
and the incident; ``scripts/verify_lock_popup_safety.py`` is the behavioural
half of this guard and proves the fix still holds under a live recovery tick
(run by the ``lock-popup-safety`` job in ``.github/workflows/python-tests.yml``).

The set of modules under the ban is DERIVED, not listed: anything in the
package that both imports ``tkinter`` and paints onto the shared container is
in scope automatically, so a new lock screen is covered the day it is written
rather than the day someone remembers to add it here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parent.parent

EXEMPT: dict[str, str] = {
    "status_view.py": "plain tk.Tk with no grab and no recovery loop",
    "_heat_skip.py": "own throwaway root, destroyed before the lock exists",
}
"""Modules that touch Tk but never paint onto a gatelock lock surface.

Kept deliberately short and reasoned: every entry is a module allowed to open
a popup, so an unjustified addition here is how the guard gets hollowed out.
"""

BANNED = frozenset(
    {
        "OptionMenu",
        "Combobox",
        "tk_popup",
        "post",
        "messagebox",
        "simpledialog",
        "filedialog",
        "colorchooser",
        "Toplevel",
    }
)


def lock_surface_modules() -> list[str]:
    """Every package module that touches Tk on behalf of the lock window.

    Importing ``tkinter`` is the whole test: the mixins build into a parent
    handed to them, so there is no reliable in-module marker saying "this ends
    up on a surface". Anything that genuinely does not is named in ``EXEMPT``
    with its reason.
    """
    return [
        path.name
        for path in sorted(PACKAGE_DIR.glob("*.py"))
        if "import tkinter" in path.read_text(encoding="utf-8")
        and path.name not in EXEMPT
    ]


def symbols(module_name: str) -> set[str]:
    """Every attribute and bare name referenced in a module's code.

    An AST walk rather than a source regex: every banned widget is either an
    ``ast.Attribute`` (``tk.OptionMenu``) or an ``ast.Name`` (a bare import),
    so docstrings, comments and string literals are excluded for free. The
    modules under test explain this very bug in prose that names the banned
    widgets, and a regex would have to strip that back out.
    """
    tree = ast.parse((PACKAGE_DIR / module_name).read_text(encoding="utf-8"))
    return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    }


def test_the_module_list_is_not_empty() -> None:
    """A derived list that silently went empty would pass every other test."""
    assert lock_surface_modules(), (
        "no lock-surface modules detected -- the markers in _SURFACE_MARKERS "
        "have probably drifted, which would make this whole guard a no-op"
    )


@pytest.mark.parametrize("module_name", lock_surface_modules())
def test_lock_surface_module_creates_no_popup(module_name: str) -> None:
    """Fail if a lock-surface module references any popup-creating API."""
    offenders = sorted(symbols(module_name) & BANNED)
    assert not offenders, (
        f"{module_name} uses popup-creating Tk API {offenders}; a popup on a "
        "lock surface is covered and loses its grab within one recovery tick"
    )
