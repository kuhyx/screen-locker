"""Tests for _rtdb_stream: the SSE line parser and the put/patch normaliser."""

from __future__ import annotations

import json

import pytest

from screen_locker._rtdb_stream import SseEvent, device_updates, parse_sse

_LEAF = "log~2Ejson"


def _event(name: str, path: str, data: object) -> SseEvent:
    """A ``put``/``patch`` event carrying ``{path, data}`` as RTDB sends it."""
    return SseEvent(name, json.dumps({"path": path, "data": data}))


class TestParseSse:
    """Server-Sent Events framing: a blank line ends each event."""

    def test_named_event_with_data(self) -> None:
        """``event:`` + ``data:`` + blank line yields one event."""
        lines = ["event: put", 'data: {"path":"/"}', ""]
        assert list(parse_sse(lines)) == [SseEvent("put", '{"path":"/"}')]

    def test_multiple_data_lines_are_joined_with_newlines(self) -> None:
        """Per the SSE spec, repeated ``data:`` lines join with ``\\n``."""
        events = list(parse_sse(["event: patch", "data: a", "data:   b", ""]))
        assert events == [SseEvent("patch", "a\nb")]

    def test_no_space_after_colon_is_accepted(self) -> None:
        """``event:put`` is as valid as ``event: put``."""
        assert list(parse_sse(["event:keep-alive", "data:null", ""])) == [
            SseEvent("keep-alive", "null")
        ]

    def test_data_without_event_is_a_message(self) -> None:
        """An unnamed event defaults to ``message``."""
        assert list(parse_sse(["data: hi", ""])) == [SseEvent("message", "hi")]

    def test_event_without_data_still_yields(self) -> None:
        """A name alone is an event (``cancel`` may carry no data)."""
        assert list(parse_sse(["event: cancel", ""])) == [SseEvent("cancel", "")]

    def test_stray_blank_lines_and_comments_yield_nothing(self) -> None:
        """Blank separators and ``:`` comments / unknown fields are ignored."""
        assert list(parse_sse(["", "", ": comment", "id: 7", "retry: 5", ""])) == []

    def test_back_to_back_events_do_not_leak_state(self) -> None:
        """Each event starts with a clean name and data."""
        lines = ["event: put", "data: 1", "", "data: 2", ""]
        assert list(parse_sse(lines)) == [
            SseEvent("put", "1"),
            SseEvent("message", "2"),
        ]

    def test_unterminated_event_is_not_emitted(self) -> None:
        """Without the closing blank line the event is incomplete: dropped."""
        assert list(parse_sse(["event: put", "data: 1"])) == []


class TestDeviceUpdatesPut:
    """``put`` events: the data replaces whatever sits at the path."""

    def test_root_put_is_a_full_snapshot(self) -> None:
        """``put /`` carries every device; the caller must REPLACE its cache."""
        data = {"phone": {_LEAF: "TEXT-P"}, "pc": {_LEAF: "TEXT-C"}}
        full, updates = device_updates(_event("put", "/", data))
        assert full is True
        assert updates == {"phone": "TEXT-P", "pc": "TEXT-C"}

    def test_root_put_with_null_is_an_empty_snapshot(self) -> None:
        """An empty devices node arrives as ``data: null``."""
        assert device_updates(_event("put", "/", None)) == (True, {})

    def test_root_put_decodes_plain_and_escaped_leaf_keys(self) -> None:
        """The leaf may arrive as ``log.json`` or the escaped ``log~2Ejson``."""
        data = {"a": {"log.json": "X"}, "b": {_LEAF: "Y"}}
        assert device_updates(_event("put", "/", data))[1] == {"a": "X", "b": "Y"}

    def test_root_put_device_without_log_is_none(self) -> None:
        """A device node that is not a dict, lacks the leaf or holds a non-string."""
        data = {"a": "scalar", "b": {"other": "x"}, "c": {_LEAF: 5}, "d": None}
        updates = device_updates(_event("put", "/", data))[1]
        assert updates == {"a": None, "b": None, "c": None, "d": None}

    def test_root_put_with_non_object_is_a_type_error(self) -> None:
        """A devices node that is not an object is a protocol violation."""
        with pytest.raises(TypeError, match="not an object"):
            device_updates(_event("put", "/", ["x"]))

    def test_device_level_put(self) -> None:
        """``put /phone`` replaces one device's node."""
        full, updates = device_updates(_event("put", "/phone", {_LEAF: "T"}))
        assert (full, updates) == (False, {"phone": "T"})

    def test_device_level_delete(self) -> None:
        """``put /phone`` with null removes the log."""
        assert device_updates(_event("put", "/phone", None)) == (False, {"phone": None})

    def test_leaf_level_put_and_delete(self) -> None:
        """``put /phone/log~2Ejson`` sets or clears the text directly."""
        path = f"/phone/{_LEAF}"
        assert device_updates(_event("put", path, "T")) == (False, {"phone": "T"})
        assert device_updates(_event("put", path, None)) == (False, {"phone": None})

    def test_leaf_level_put_of_non_string_is_none(self) -> None:
        """A non-text leaf is not a log: the device has none."""
        assert device_updates(_event("put", f"/phone/{_LEAF}", 7)) == (
            False,
            {"phone": None},
        )

    def test_put_below_the_log_leaf_is_irrelevant(self) -> None:
        """Anything under a device that is not its log changes nothing."""
        assert device_updates(_event("put", "/phone/other", "x")) == (False, {})

    def test_device_ids_are_decoded(self) -> None:
        """Escaped device names (``~2E``) come back as the real id."""
        assert device_updates(_event("put", "/pc~2E1", {_LEAF: "T"}))[1] == {
            "pc.1": "T"
        }


class TestDeviceUpdatesPatch:
    """``patch`` events: several children, keys may be multi-segment paths."""

    def test_patch_with_leaf_paths(self) -> None:
        """Each key is resolved relative to the event path."""
        data = {f"phone/{_LEAF}": "T1", f"pc/{_LEAF}": None}
        full, updates = device_updates(_event("patch", "/", data))
        assert full is False
        assert updates == {"phone": "T1", "pc": None}

    def test_patch_with_device_keys_and_base_path(self) -> None:
        """A patch at ``/phone`` with a bare leaf key targets that device."""
        data = {_LEAF: "T"}
        assert device_updates(_event("patch", "/phone", data)) == (
            False,
            {"phone": "T"},
        )

    def test_patch_at_root_is_never_a_snapshot(self) -> None:
        """Even at ``/``, a patch merges; it must not replace the cache."""
        assert device_updates(_event("patch", "/", {"phone": {_LEAF: "T"}}))[0] is False

    def test_patch_with_non_object_data_is_a_type_error(self) -> None:
        """``patch`` data must be an object."""
        with pytest.raises(TypeError, match="patch data is str"):
            device_updates(_event("patch", "/", "oops"))


class TestDeviceUpdatesMalformed:
    """Garbage must raise, so the caller can warn instead of guessing."""

    def test_non_json_data_is_a_value_error(self) -> None:
        """Unparsable data raises ``ValueError``."""
        with pytest.raises(json.JSONDecodeError):
            device_updates(SseEvent("put", "{not json"))

    @pytest.mark.parametrize(
        "data", ["[]", "null", '"x"', '{"data": 1}', '{"path": 3, "data": 1}']
    )
    def test_missing_or_bad_path_is_a_type_error(self, data: str) -> None:
        """Anything but ``{path: str, data: ...}`` is rejected."""
        with pytest.raises(TypeError, match="without a path"):
            device_updates(SseEvent("put", data))
