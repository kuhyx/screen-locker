"""Re-run a GUI check script on a throwaway X display.

Split out of ``verify_lock_popup_safety.py`` and ``verify_screen_fits.py``
to keep every file under the 250-line cap. Both had their own near-identical
copy; they differ only in the sentinel env var and how the inner process is
addressed, so both are parameters here.

Each script runs itself twice: the outer run starts ``xvfb-run`` and re-execs,
the inner run (marked by the sentinel) does the real work against that
display. Without the sentinel the inner process would start another Xvfb
forever.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys

_logger = logging.getLogger(__name__)

# Comfortably bigger than every size under test, so each surface is sized by
# the geometry the harness sets rather than clamped by the display.
_SCREEN_ARG = "-screen 0 1600x1200x24"


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
        The inner process's exit code, or 1 if ``xvfb-run`` is unavailable.
    """
    if (module is None) == (script is None):
        msg = "pass exactly one of module= or script="
        raise ValueError(msg)

    xvfb_run = shutil.which("xvfb-run")
    if xvfb_run is None:
        _logger.error(
            "xvfb-run not found. Install it with: sudo pacman -S --needed "
            "xorg-server-xvfb"
        )
        return 1

    env = dict(os.environ, **{inner_env: "1"})
    repo_root = Path(__file__).resolve().parent.parent
    # Absolute argv, no shell.
    target = ["-m", module] if module is not None else [str(script)]
    return subprocess.run(
        [xvfb_run, "-a", "-s", _SCREEN_ARG, sys.executable, *target],
        check=False,
        cwd=repo_root,
        env=env,
    ).returncode
