"""Render the two pace-cue tones with the standard library only.

Falling tone (``pace_slow.wav``): speed up. Rising tone (``pace_fast.wav``):
ease off. Each is two soft sine notes with a fast attack and a linear fade so
nothing clicks. They sit apart in pitch and direction, so they can be told
apart with the screen off and the phone in a pocket (the vibration pattern is
the second channel).

Usage: ``render_pace_tones.py OUT_DIR`` writes both files into OUT_DIR and
adds their entries (recipe, frame count, SHA-256) to OUT_DIR/MANIFEST.json,
leaving the other entries (the finish chime's) as they are. Standard library
only, so there is no toolkit to pin and no ``.sh`` wrapper.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import wave

SAMPLE_RATE = 44100
PEAK = 0.6
ATTACK_SECONDS = 0.01
# (frequency in Hz, seconds) per note.
SLOW_NOTES = ((494.0, 0.22), (370.0, 0.34))
FAST_NOTES = ((880.0, 0.11), (1319.0, 0.17))
ARG_COUNT = 2


def _note(freq: float, seconds: float) -> list[float]:
    """One sine note with an attack ramp and a linear fade to zero."""
    count = int(SAMPLE_RATE * seconds)
    attack = int(SAMPLE_RATE * ATTACK_SECONDS)
    samples = []
    for i in range(count):
        gain = min(1.0, i / attack) * (1 - i / count)
        samples.append(PEAK * gain * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
    return samples


def render(path: Path, notes: tuple[tuple[float, float], ...]) -> dict[str, object]:
    """Write ``notes`` back to back as a 16-bit mono WAV; return its manifest entry."""
    samples = [s for freq, seconds in notes for s in _note(freq, seconds)]
    with wave.Wave_write(str(path)) as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
    return {
        "file": path.name,
        "frames": len(samples),
        "recipe": {
            "attack_seconds": ATTACK_SECONDS,
            "notes": [list(note) for note in notes],
            "peak": PEAK,
            "sample_rate": SAMPLE_RATE,
        },
        "sample_rate": SAMPLE_RATE,
        "seconds": round(len(samples) / SAMPLE_RATE, 2),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def update_manifest(path: Path, entries: dict[str, dict[str, object]]) -> None:
    """Merge ``entries`` into the JSON manifest at ``path``, keeping the rest."""
    manifest: dict[str, object] = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    )
    manifest.update(entries)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: list[str]) -> int:
    """Render both tones into the directory named by ``argv[1]``."""
    if len(argv) != ARG_COUNT:
        sys.stderr.write("usage: render_pace_tones.py OUT_DIR\n")
        return 2
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    entries = {
        "pace_slow.wav": render(out / "pace_slow.wav", SLOW_NOTES),
        "pace_fast.wav": render(out / "pace_fast.wav", FAST_NOTES),
    }
    update_manifest(out / "MANIFEST.json", entries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
