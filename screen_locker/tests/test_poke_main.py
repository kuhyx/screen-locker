"""The poke daemon CLI: key loading, startup refusals, stream wiring."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, ClassVar
from unittest.mock import MagicMock

import pytest

from screen_locker import _poke_credit, poke_server
from screen_locker._poke_server import POKE_PATH

if TYPE_CHECKING:
    from pathlib import Path

_KEY_HEX = "ab" * 32


def _key_file(tmp_path: Path, text: str = _KEY_HEX, mode: int = 0o600) -> Path:
    path = tmp_path / "key"
    path.write_text(text, encoding="ascii")
    path.chmod(mode)
    return path


class FakeServer:
    """Stands in for PokeServer: records how the daemon drove it."""

    instances: ClassVar[list[FakeServer]] = []

    def __init__(self, address: tuple[str, int], key: bytes) -> None:
        self.address = address
        self.key = key
        self.gate = threading.Lock()
        self.closed = False
        self.instances.append(self)

    def serve_forever(self) -> None:
        return

    def server_close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _daemon_stubs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No real budget sum or server socket in any test here."""
    FakeServer.instances.clear()
    locker = MagicMock()
    locker.log_file = tmp_path / "log.json"
    monkeypatch.setattr(_poke_credit, "fresh_locker", lambda: locker)
    monkeypatch.setattr(_poke_credit, "current_shutdown", MagicMock())
    monkeypatch.setattr(_poke_credit, "current_gaming_minutes", MagicMock())
    monkeypatch.setattr(poke_server, "PokeServer", FakeServer)


@pytest.fixture(autouse=True)
def stream(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The Firebase stream class; never a real connection."""
    stub = MagicMock()
    monkeypatch.setattr(poke_server, "SessionStream", stub)
    return stub


class TestLoadKey:
    def test_reads_a_600_key(self, tmp_path: Path) -> None:
        assert poke_server.load_key(_key_file(tmp_path)) == bytes.fromhex(_KEY_HEX)

    @pytest.mark.parametrize("mode", [0o640, 0o604, 0o660, 0o644])
    def test_group_or_world_access_is_refused_with_the_fix(
        self, tmp_path: Path, mode: int
    ) -> None:
        with pytest.raises(ValueError, match="chmod 600"):
            poke_server.load_key(_key_file(tmp_path, mode=mode))

    def test_malformed_key_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="hex"):
            poke_server.load_key(_key_file(tmp_path, text="short"))

    def test_missing_file_raises_oserror(self, tmp_path: Path) -> None:
        with pytest.raises(OSError, match="key"):
            poke_server.load_key(tmp_path / "key")


class TestMain:
    def test_missing_key_refuses_to_start_at_critical(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.CRITICAL):
            code = poke_server.main(["--key-file", str(tmp_path / "nope")])
        assert code == 1
        assert "bad poke key" in caplog.text
        assert "workout_poke_keygen.sh" in caplog.text
        assert not FakeServer.instances

    def test_loose_key_mode_refuses_to_start(self, tmp_path: Path) -> None:
        key = _key_file(tmp_path, mode=0o644)
        assert poke_server.main(["--key-file", str(key)]) == 1
        assert not FakeServer.instances

    def test_bind_failure_refuses_to_start_at_critical(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def busy(_address: tuple[str, int], _key: bytes) -> Any:
            msg = "address in use"
            raise OSError(msg)

        monkeypatch.setattr(poke_server, "PokeServer", busy)
        with caplog.at_level(logging.CRITICAL):
            code = poke_server.main(
                ["--key-file", str(_key_file(tmp_path)), "--port", "9"]
            )
        assert code == 1
        assert "cannot bind :9 (address in use)" in caplog.text

    def test_serves_with_the_key_and_starts_the_stream(
        self,
        tmp_path: Path,
        stream: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        argv = ["--key-file", str(_key_file(tmp_path)), "--port", "1234"]
        with caplog.at_level(logging.INFO):
            code = poke_server.main([*argv, "--bind", "127.0.0.1"])
        (server,) = FakeServer.instances
        assert code == 0
        assert server.address == ("127.0.0.1", 1234)
        assert server.key == bytes.fromhex(_KEY_HEX)
        assert server.closed
        stream.assert_called_once_with(server.gate)
        stream.return_value.start.assert_called_once_with()
        assert f"127.0.0.1:1234{POKE_PATH}" in caplog.text
        assert isinstance(_poke_credit.current_shutdown, MagicMock)
        _poke_credit.current_shutdown.assert_called_once_with()

    def test_default_bind_is_all_interfaces_on_the_default_port(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO):
            poke_server.main(["--key-file", str(_key_file(tmp_path))])
        assert FakeServer.instances[0].address == ("", poke_server.DEFAULT_PORT)
        assert f"*:{poke_server.DEFAULT_PORT}" in caplog.text

    def test_no_stream_skips_firebase_and_says_so(
        self,
        tmp_path: Path,
        stream: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.WARNING):
            code = poke_server.main(
                ["--key-file", str(_key_file(tmp_path)), "--no-stream"]
            )
        assert code == 0
        stream.assert_not_called()
        assert "disabled by --no-stream" in caplog.text
        assert FakeServer.instances[0].closed

    def test_stream_failure_never_stops_the_lan_poke(
        self,
        tmp_path: Path,
        stream: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        stream.return_value.start.side_effect = RuntimeError("no network")
        with caplog.at_level(logging.ERROR):
            code = poke_server.main(["--key-file", str(_key_file(tmp_path))])
        assert code == 0
        assert "Could not start the Firebase session stream" in caplog.text
        assert FakeServer.instances[0].closed

    def test_server_is_closed_even_when_serving_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(_self: FakeServer) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(FakeServer, "serve_forever", explode)
        with pytest.raises(KeyboardInterrupt):
            poke_server.main(["--key-file", str(_key_file(tmp_path))])
        assert FakeServer.instances[0].closed
