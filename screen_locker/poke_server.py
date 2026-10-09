"""``python3 -m screen_locker.poke_server``: the phone -> PC workout poke daemon.

What ``workout-poke.service`` runs: load the shared key, warm the imports and
the budget sum, start the Firebase session stream (off-LAN credit,
:mod:`screen_locker._session_stream`) on a daemon thread, then serve ``POST
/v1/workout`` on port 8773 for good. The request handling lives in
:mod:`screen_locker._poke_server`; the contract is
``docs/DOCS-workout-poke-contract.md``.

A missing, malformed or group/world-readable key is a refusal to start,
logged at critical, so ``systemctl --user status workout-poke`` says why.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import stat
import sys
from typing import Final

from screen_locker import _poke_credit
from screen_locker._poke_server import POKE_PATH, PokeServer
from screen_locker._poke_wire import parse_key
from screen_locker._session_stream import SessionStream

__all__ = ["DEFAULT_KEY_FILE", "DEFAULT_PORT", "load_key", "main"]

_logger: Final = logging.getLogger(__name__)

DEFAULT_PORT: Final = 8773
DEFAULT_KEY_FILE: Final = Path.home() / ".config" / "workout_poke" / "key"
_KEYGEN_HINT: Final = "run scripts/workout_poke_keygen.sh"


def load_key(path: Path) -> bytes:
    """Read the shared key; refuse a world/group-readable or malformed one.

    Raises:
        ValueError: With a sentence naming the problem and the fix.
        OSError: The file cannot be read (usually: it does not exist).
    """
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        msg = f"{path} has mode {mode:o}; it must be 600 (chmod 600 {path})"
        raise ValueError(msg)
    return parse_key(path.read_text(encoding="ascii"))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # "" binds every interface; the firewall admits tcp/8773 from the LAN only.
    parser.add_argument("--bind", default="", help="address (default: all)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE)
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="skip the Firebase stream (off-LAN credit falls back to the sync)",
    )
    return parser.parse_args(argv)


def _start_stream(server: PokeServer) -> None:
    """Start the Firebase session stream; a failure here never stops the LAN poke."""
    try:
        # Same lock as the HTTP handler: a poke and a streamed copy of one
        # session must never be credited concurrently.
        SessionStream(server.gate).start()
    except Exception:
        _logger.exception(
            "Could not start the Firebase session stream; off-LAN workouts will "
            "only be credited by the 15-min workout-sync until the daemon restarts"
        )


def main(argv: list[str] | None = None) -> int:
    """Load the key, warm up, serve forever; 1 (logged critical) if it cannot."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args(argv)
    try:
        key = load_key(args.key_file)
    except (OSError, ValueError) as exc:
        _logger.critical("Refusing to start: bad poke key (%s); %s", exc, _KEYGEN_HINT)
        return 1
    # Warm the budget sum (registry, ledgers) and the conf read once, so the
    # first poke costs what every later one does.
    _poke_credit.current_shutdown()
    _poke_credit.current_gaming_minutes(_poke_credit.fresh_locker().log_file)
    try:
        server = PokeServer((args.bind, args.port), key)
    except OSError as exc:
        _logger.critical(
            "Refusing to start: cannot bind %s:%d (%s)", args.bind, args.port, exc
        )
        return 1
    _logger.info(
        "Workout poke listening on %s:%d%s", args.bind or "*", args.port, POKE_PATH
    )
    if args.no_stream:
        _logger.warning(
            "Firebase session stream disabled by --no-stream; off-LAN workouts "
            "will only be credited by the 15-min workout-sync"
        )
    else:
        _start_stream(server)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
