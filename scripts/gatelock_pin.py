"""Compare a gatelock against the version screen-locker pins (install.sh's gate).

install.sh re-installs the ~/src/utils/gatelock clone editable so unreleased
gatelock work reaches the lock. That is only right while the clone is at least
the pinned release: on 2026-11-27 a stale clone (0.16.0) was re-asserted over
the 0.16.2 pin and the stall fix never reached the running lock.

CLI (exit 0 ok, 1 older than the pin, 2 unreadable/usage):
  gatelock_pin.py clone-ok PYPROJECT CLONE_DIR   clone may be made editable
  gatelock_pin.py installed-ok PYPROJECT         imported gatelock is current
  gatelock_pin.py spec PYPROJECT                 print the pinned pip spec
"""

from __future__ import annotations

from importlib import metadata
import logging
from pathlib import Path
import re
import sys
import tomllib

_logger = logging.getLogger("gatelock_pin")

EXIT_OK = 0
EXIT_OLDER = 1
EXIT_ERROR = 2

_PIN = re.compile(r"^gatelock\s*@.*@gatelock-v(?P<v>[0-9][0-9.]*)#")

Version = tuple[int, ...]


class PinError(ValueError):
    """A version that cannot be read: the gate fails closed on it."""


def _parse(text: str) -> Version:
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError as exc:
        msg = f"not a release version: {text!r}"
        raise PinError(msg) from exc


def _project(path: Path) -> dict[str, object]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"cannot read {path}: {exc}"
        raise PinError(msg) from exc
    project = data.get("project", {})
    return project if isinstance(project, dict) else {}


def _pin(pyproject: Path) -> re.Match[str]:
    for dep in _project(pyproject).get("dependencies", []):
        match = _PIN.match(str(dep))
        if match:
            return match
    msg = f"no gatelock pin in {pyproject}"
    raise PinError(msg)


def pinned_spec(pyproject: Path) -> str:
    """Return the gatelock dependency string pinned in ``pyproject``."""
    return _pin(pyproject).string


def pinned_version(pyproject: Path) -> Version:
    """Return the gatelock tag version pinned in ``pyproject``'s dependencies."""
    return _parse(_pin(pyproject)["v"].rstrip("."))


def clone_version(clone: Path) -> Version:
    """Return the version a gatelock source clone declares."""
    return _parse(str(_project(clone / "pyproject.toml").get("version", "")))


def installed_version() -> Version:
    """Return the version of the gatelock this interpreter imports."""
    return _parse(metadata.version("gatelock"))


def _show(version: Version) -> str:
    return ".".join(map(str, version))


def _check(what: str, have: Version, pin: Version) -> int:
    if have < pin:
        _logger.error(
            "gatelock %s %s is older than the pin %s", what, _show(have), _show(pin)
        )
        return EXIT_OLDER
    _logger.warning("gatelock %s %s >= pin %s", what, _show(have), _show(pin))
    return EXIT_OK


def main(argv: list[str]) -> int:
    """Run one check; see the module docstring for the exit codes."""
    try:
        match argv:
            case ["clone-ok", pyproject, clone]:
                pin = pinned_version(Path(pyproject))
                return _check("clone", clone_version(Path(clone)), pin)
            case ["installed-ok", pyproject]:
                pin = pinned_version(Path(pyproject))
                return _check("installed", installed_version(), pin)
            case ["spec", pyproject]:
                sys.stdout.write(pinned_spec(Path(pyproject)) + "\n")
                return EXIT_OK
            case _:
                _logger.error("usage:%s", __doc__)
                return EXIT_ERROR
    except PinError, metadata.PackageNotFoundError:
        # Fail closed: install.sh treats any non-zero exit as untrusted.
        _logger.exception("gatelock version gate failed")
        return EXIT_ERROR


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s")
    sys.exit(main(sys.argv[1:]))
