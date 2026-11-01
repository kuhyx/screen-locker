"""Render the finish-workout chime with the pinned music_theory toolkit.

Recipe, in words: a C major arpeggio (C5 E5 G5 C6) struck in quick succession
-- rising, so it reads as "arrived" -- each note a sine with a quiet third
harmonic for a bell-like edge, decaying to silence. Major because the cue
confirms that a workout was RECORDED; it is identical for a deloaded or
failed workout, on purpose (reward the recording, never the number).

Usage: ``render_finish_chime.py OUT_DIR`` writes ``workout_done.wav`` and
``MANIFEST.json`` (recipe, toolkit version, SHA-256) into OUT_DIR.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import sys

from music_theory import analysis, manifest, sequencer, synth, wav

SAMPLE_RATE = 44100
TEMPO_BPM = 240.0
# Beats are 0.25 s at 240 bpm: a note every 0.2 beat is 50 ms.
NOTE_STEP_BEATS = 0.2
CHIME_NOTES = (72, 76, 79, 84)
# A struck bell: near-instant attack, then a decay all the way to zero.
BELL = synth.Envelope(attack=0.003, decay=0.35, sustain=0.0, release=0.05)
RING_BEATS = 1.6
HARMONIC_GAIN = 0.2
# The third harmonic sits an octave and a fifth up: 3:1 is 19.02 semitones.
THIRD_HARMONIC_SEMITONES = 19
PEAK = 0.7
ARG_COUNT = 2
FILE_NAME = "workout_done.wav"


@dataclass(frozen=True)
class ChimeRecipe:
    """Everything that decides the chime; recorded verbatim in the manifest."""

    notes: tuple[int, ...] = CHIME_NOTES
    tempo_bpm: float = TEMPO_BPM
    note_step_beats: float = NOTE_STEP_BEATS
    ring_beats: float = RING_BEATS
    harmonic_gain: float = HARMONIC_GAIN
    sample_rate: int = SAMPLE_RATE

    def to_dict(self) -> dict[str, object]:
        """JSON-ready form for the manifest."""
        data = asdict(self)
        data["notes"] = list(self.notes)
        return data


def _voice(recipe: ChimeRecipe, shift: int, velocity: float) -> synth.Signal:
    """The arpeggio, every note moved up ``shift`` semitones."""
    events = [
        sequencer.NoteEvent(
            midi + shift,
            index * recipe.note_step_beats,
            recipe.ring_beats,
            velocity,
            "sine",
            BELL,
        )
        for index, midi in enumerate(recipe.notes)
    ]
    length = (len(recipe.notes) - 1) * recipe.note_step_beats + recipe.ring_beats
    return sequencer.render(events, recipe.tempo_bpm, length, recipe.sample_rate)


def render_chime(recipe: ChimeRecipe) -> synth.Signal:
    """The finished chime: fundamental plus a quiet third harmonic."""
    body = _voice(recipe, 0, 1.0)
    shimmer = _voice(recipe, THIRD_HARMONIC_SEMITONES, recipe.harmonic_gain)
    return synth.normalize(synth.mix(body, shimmer), PEAK)


def main(argv: list[str]) -> int:
    """Render into the directory named by ``argv[1]``."""
    if len(argv) != ARG_COUNT:
        sys.stderr.write("usage: render_finish_chime.py OUT_DIR\n")
        return 2
    out_dir = Path(argv[1])
    recipe = ChimeRecipe()
    signal = render_chime(recipe)
    path = wav.write(out_dir / FILE_NAME, signal, recipe.sample_rate)
    manifest.write(
        out_dir / "MANIFEST.json", {FILE_NAME: manifest.entry(recipe, path, signal)}
    )
    seconds = len(signal) / recipe.sample_rate
    centroid = analysis.spectral_centroid(signal, recipe.sample_rate)
    sys.stdout.write(
        f"{path.name}: {seconds:.2f} s, centroid {centroid:.0f} Hz, "
        f"sha256 {wav.sha256(path)[:12]}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
