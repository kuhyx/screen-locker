"""Re-run a GUI check script on a throwaway X display.

Split out of ``verify_lock_popup_safety.py`` and ``verify_screen_fits.py``
to keep every file under the 250-line cap. Both had their own near-identical
copy; they differ only in the sentinel env var and how the inner process is
addressed, so both are parameters here.

Each script runs itself twice: the outer run starts ``Xvfb`` and re-execs,
the inner run (marked by the sentinel) does the real work against that
display. Without the sentinel the inner process would start another Xvfb
forever.
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_logger = logging.getLogger(__name__)

# Comfortably bigger than every size under test, so each surface is sized by
# the geometry the harness sets rather than clamped by the display.
_SCREEN_ARG = ("-screen", "0", "1600x1200x24")


def reexec_under_xvfb(
    *,
    inner_env: str,
    module: str | None = None,
    script: Path | None = None,
) -> int:
    """Re-run this check on a throwaway X display, returning its exit code.

    Exactly one of *module* (run as ``python -m module`` from the repo root)
    or *script* (run as an absolute path) identifies the inner process; that
    difference is why the two callers cannot share a single hardcoded form.

    Args:
        inner_env: Sentinel env var set for the inner run, so it knows not to
            start another Xvfb.
        module: Dotted module path to run with ``-m``.
        script: Absolute path of the script file to run.

    Returns:
        The inner process's exit code, or 1 if ``Xvfb`` is unavailable or
        never became ready.
    """
    if (module is None) == (script is None):
        msg = "pass exactly one of module= or script="
        raise ValueError(msg)

    xvfb = shutil.which("Xvfb")
    if xvfb is None:
        _logger.error(
            "Xvfb not found. Install it with: sudo pacman -S --needed xorg-server-xvfb"
        )
        return 1

    repo_root = Path(__file__).resolve().parent.parent
    # Absolute argv, no shell.
    target = ["-m", module] if module is not None else [str(script)]
    with _xvfb_display(xvfb) as display:
        if display is None:
            _logger.error("Xvfb exited before it was ready to accept clients")
            return 1
        env = dict(os.environ, DISPLAY=display, **{inner_env: "1"})
        env.pop("XAUTHORITY", None)  # a throwaway server has no cookie to check
        return subprocess.run(
            [sys.executable, *target], check=False, cwd=repo_root, env=env
        ).returncode


@contextlib.contextmanager
def _xvfb_display(xvfb: str) -> Iterator[str | None]:
    """Run Xvfb on a free display; yield ``:N`` once ready (``None`` if it died).

    ``-displayfd`` makes Xvfb pick a free display and write its number only
    once it accepts clients. ``xvfb-run`` instead sleeps a fixed 3 s after
    starting it, which was most of this pre-commit hook's runtime.
    """
    read_fd, write_fd = os.pipe()
    with subprocess.Popen(
        [xvfb, "-displayfd", str(write_fd), "-nolisten", "tcp", *_SCREEN_ARG],
        pass_fds=(write_fd,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as server:
        os.close(write_fd)
        try:
            with os.fdopen(read_fd) as ready:
                number = ready.readline().strip()
            yield f":{number}" if number else None
        finally:
            server.terminate()
            server.wait(timeout=5)
