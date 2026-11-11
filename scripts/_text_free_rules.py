"""What counts as a painted word for ``verify_text_free``.

Content is allowed (textgate-rework R4): numbers, dates, symbols, glyphs, and
a unit symbol written right after its number (``31°C``, ``5 km``,
``40 min``). Everything else with two or more letters in a row is chrome
someone wrote around the content, and the check fails on it.
"""

from __future__ import annotations

import re

# A unit symbol glued to (or one space after) the number it measures.
_UNIT_AFTER_NUMBER = re.compile(r"(?<=\d)\s?(?:kg|km|min|h|ms)\b")
_WORD = re.compile(r"[A-Za-z]{2,}")


def words_in(text: str) -> list[str]:
    """Return every chrome word in *text* (empty list when text-free)."""
    return _WORD.findall(_UNIT_AFTER_NUMBER.sub("", text))
