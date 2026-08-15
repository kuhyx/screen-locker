"""Split a Dart test file at top-level `group(` boundaries.

Each output file reuses the original's imports and its main() setup preamble
(everything between `void main() {` and the first top-level group), so every
part runs the same fixtures the original did.

Usage:
    split_dart_test.py <file> <out1>:<firstGroupIdx> [<out2>:<idx> ...]

Indices are 0-based positions in the top-level group list; each output takes
groups[idx:next_idx]. The source file keeps groups[:first_idx].
"""

from __future__ import annotations

from pathlib import Path
import re
import sys


def top_level_groups(lines: list[str]) -> list[int]:
    """Return 0-based line indices of every top-level test boundary.

    Screen tests are often a flat list of `testWidgets(` calls with no
    `group(` at all, so both count as a split point.
    """
    return [
        i
        for i, ln in enumerate(lines)
        if re.match(r"^  (group|testWidgets|test)\(", ln)
    ]


def split(path: Path, specs: list[tuple[Path, int]]) -> None:
    """Write each spec's group range to its own file, trimming the source."""
    lines = path.read_text().splitlines(keepends=True)
    groups = top_level_groups(lines)
    main_idx = next(i for i, ln in enumerate(lines) if ln.startswith("void main("))
    header = "".join(lines[:main_idx])
    preamble = "".join(lines[main_idx + 1 : groups[0]])

    # Fixtures and fake classes often sit AFTER main(). Every split file needs
    # them too, or it fails to compile on a helper the original defined once.
    main_end = next(
        (i for i in range(len(lines) - 1, main_idx, -1) if lines[i].startswith("}")),
        len(lines) - 1,
    )
    trailer = "".join(lines[main_end + 1 :])

    bounds = [i for _, i in specs] + [len(groups)]
    for (out, start), end in zip(specs, bounds[1:], strict=False):
        first = groups[start]
        last = groups[end] if end < len(groups) else main_end
        body = "".join(lines[first:last]).rstrip("\n")
        out.write_text(f"{header}void main() {{\n{preamble}{body}\n}}\n{trailer}")

    keep = groups[specs[0][1]]
    path.write_text(
        "".join(lines[:keep]).rstrip("\n") + "\n}\n" + trailer,
    )


def main() -> int:
    """Parse argv and run the split."""
    src = Path(sys.argv[1])
    specs = []
    for arg in sys.argv[2:]:
        name, idx = arg.rsplit(":", 1)
        specs.append((src.parent / name, int(idx)))
    split(src, specs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
