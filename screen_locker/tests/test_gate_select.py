"""Selection of push-gate tests from a change set (scripts/gate_select.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts import gate_select as gs

if TYPE_CHECKING:
    from pathlib import Path

APP = gs.APP


def _write(root: Path, rel: str, text: str = "") -> None:
    path = root / APP / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _tree(root: Path) -> None:
    _write(root, "lib/a.dart", "")
    _write(root, "lib/b.dart", "import 'a.dart';")
    _write(root, "lib/c.dart", "import 'package:workout_app/b.dart' if (x) 'a.dart';")
    _write(root, "lib/lonely.dart", "")
    _write(root, "test/rig.dart", "import 'package:workout_app/lonely.dart';")
    _write(root, "test/c_test.dart", "import 'package:workout_app/c.dart';")
    _write(root, "test/lonely_test.dart", "import 'rig.dart';")
    _write(root, "test/sub/x_test.dart", "import '../rig.dart';")
    _write(root, "test/other_test.dart", "import 'dart:io';")


def test_transitive_import_reaches_test(tmp_path: Path) -> None:
    _tree(tmp_path)
    got = gs.dart_affected_tests(tmp_path, [f"{APP}/lib/a.dart"])
    assert got == [f"{APP}/test/c_test.dart"]


def test_helper_followed_by_import(tmp_path: Path) -> None:
    _tree(tmp_path)
    got = gs.dart_affected_tests(tmp_path, [f"{APP}/test/rig.dart"])
    assert got == [f"{APP}/test/lonely_test.dart", f"{APP}/test/sub/x_test.dart"]


def test_untouched_change_selects_nothing(tmp_path: Path) -> None:
    _tree(tmp_path)
    assert gs.dart_affected_tests(tmp_path, [f"{APP}/lib/lonely.dart"]) == [
        f"{APP}/test/lonely_test.dart",
        f"{APP}/test/sub/x_test.dart",
    ]
    assert gs.dart_affected_tests(tmp_path, ["README.md"]) == []


def test_pubspec_forces_full_and_says_why(tmp_path: Path) -> None:
    _tree(tmp_path)
    sel = gs.select(tmp_path, [f"{APP}/pubspec.yaml", "web/x.ts"], [])
    assert sel.full_dart
    assert sel.web
    assert any("full Dart suite" in why for why in sel.why)


def test_python_mapping_and_full(tmp_path: Path) -> None:
    tracked = [
        "screen_locker/tests/test_foo_bar.py",
        "screen_locker/tests/test__foo.py",
    ]
    assert gs.python_tests_for(["screen_locker/_foo.py"], tracked) == (
        ["screen_locker/tests/test__foo.py", "screen_locker/tests/test_foo_bar.py"],
        False,
    )
    assert gs.python_tests_for(["screen_locker/tests/test_x.py"], tracked) == (
        ["screen_locker/tests/test_x.py"],
        False,
    )
    assert gs.python_tests_for(["pyproject.toml"], tracked) == ([], True)
    assert gs.python_tests_for(["README.md"], tracked) == ([], False)


def test_no_web_without_web_files(tmp_path: Path) -> None:
    _tree(tmp_path)
    sel = gs.select(tmp_path, [f"{APP}/lib/a.dart"], [])
    assert not sel.web
    assert not sel.full_dart
    assert sel.dart == [f"{APP}/test/c_test.dart"]
