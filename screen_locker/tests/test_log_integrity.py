"""Tests for _log_integrity HMAC signing and verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from python_pkg.screen_locker._log_integrity import (
    _generate_hmac_key,
    _load_hmac_key,
    compute_entry_hmac,
    verify_entry_hmac,
)

_HMAC_KEY_FILE_PATH = "python_pkg.shared.log_integrity.HMAC_KEY_FILE"

if TYPE_CHECKING:
    from pathlib import Path


class TestLoadHmacKey:
    """Tests for _load_hmac_key."""

    def test_loads_key_from_file(self, tmp_path: Path) -> None:
        """Test loading HMAC key from existing file."""
        key_file = tmp_path / "hmac.key"
        key_file.write_bytes(b"secret_key_bytes")
        with patch(
            _HMAC_KEY_FILE_PATH,
            key_file,
        ):
            result = _load_hmac_key()
        assert result == b"secret_key_bytes"

    def test_returns_none_on_missing_file(self, tmp_path: Path) -> None:
        """Test returns None when key file doesn't exist."""
        key_file = tmp_path / "nonexistent.key"
        with patch(
            _HMAC_KEY_FILE_PATH,
            key_file,
        ):
            result = _load_hmac_key()
        assert result is None


class TestGenerateHmacKey:
    """Tests for _generate_hmac_key."""

    def test_generates_and_writes_key(self, tmp_path: Path) -> None:
        """Test key generation creates file with 32-byte key."""
        key_file = tmp_path / "subdir" / "hmac.key"
        with patch(
            _HMAC_KEY_FILE_PATH,
            key_file,
        ):
            result = _generate_hmac_key()
        assert result is not None
        assert len(result) == 32
        assert key_file.read_bytes() == result

    def test_returns_none_on_write_failure(self) -> None:
        """Test returns None when file cannot be written."""
        with patch(
            _HMAC_KEY_FILE_PATH,
        ) as mock_path:
            mock_path.parent.mkdir.side_effect = OSError("permission denied")
            result = _generate_hmac_key()
        assert result is None


class TestComputeEntryHmac:
    """Tests for compute_entry_hmac."""

    def test_computes_hmac_for_entry(self, tmp_path: Path) -> None:
        """Test HMAC computation produces valid hex string."""
        key_file = tmp_path / "hmac.key"
        key = b"test_key_12345"
        key_file.write_bytes(key)
        entry = {"timestamp": "2025-01-01T00:00:00", "workout_data": {"type": "test"}}
        with patch(
            _HMAC_KEY_FILE_PATH,
            key_file,
        ):
            result = compute_entry_hmac(entry)
        assert result is not None
        # Verify manually
        payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        assert result == expected

    def test_returns_none_when_no_key(self, tmp_path: Path) -> None:
        """Test returns None when key file is missing."""
        key_file = tmp_path / "nonexistent.key"
        with patch(
            _HMAC_KEY_FILE_PATH,
            key_file,
        ):
            result = compute_entry_hmac({"data": "test"})
        assert result is None


class TestVerifyEntryHmac:
    """Tests for verify_entry_hmac."""

    def test_valid_hmac(self, tmp_path: Path) -> None:
        """Test verification passes with correct HMAC."""
        key_file = tmp_path / "hmac.key"
        key = b"verification_key"
        key_file.write_bytes(key)
        entry_data = {"timestamp": "2025-01-01", "workout_data": {"type": "test"}}
        payload = json.dumps(entry_data, sort_keys=True, separators=(",", ":"))
        correct_hmac = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        entry = {**entry_data, "hmac": correct_hmac}

        with patch(
            _HMAC_KEY_FILE_PATH,
            key_file,
        ):
            assert verify_entry_hmac(entry) is True

    def test_invalid_hmac(self, tmp_path: Path) -> None:
        """Test verification fails with wrong HMAC."""
        key_file = tmp_path / "hmac.key"
        key_file.write_bytes(b"verification_key")
        entry = {"timestamp": "2025-01-01", "hmac": "wrong_hmac_value"}

        with patch(
            _HMAC_KEY_FILE_PATH,
            key_file,
        ):
            assert verify_entry_hmac(entry) is False

    def test_missing_hmac_field(self) -> None:
        """Test verification fails when entry has no hmac field."""
        entry: dict[str, object] = {"timestamp": "2025-01-01"}
        assert verify_entry_hmac(entry) is False

    def test_non_string_hmac_field(self) -> None:
        """Test verification fails when hmac field is not a string."""
        entry: dict[str, object] = {"timestamp": "2025-01-01", "hmac": 12345}
        assert verify_entry_hmac(entry) is False

    def test_missing_key_file(self, tmp_path: Path) -> None:
        """Test verification fails when key file doesn't exist."""
        key_file = tmp_path / "nonexistent.key"
        entry = {"timestamp": "2025-01-01", "hmac": "some_hmac"}
        with patch(
            _HMAC_KEY_FILE_PATH,
            key_file,
        ):
            assert verify_entry_hmac(entry) is False
