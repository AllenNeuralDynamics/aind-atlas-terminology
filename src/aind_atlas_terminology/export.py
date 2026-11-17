"""Write a terminology's names and colors in formats viewers read."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from aind_atlas_terminology import lateral
from aind_atlas_terminology.terminology import Terminology


def slicer_color_table(
    terminology: Terminology,
    labels: Mapping[int, int] | Sequence[int],
    path: str | Path | None = None,
    *,
    lateralized: bool = False,
) -> str:
    """Build a 3D Slicer color table (``.ctbl``) for a label volume.

    Parameters
    ----------
    terminology : Terminology
        Supplies names and colors.
    labels : mapping of int to int, or sequence of int
        Label in the volume -> annotation value it stands for. A sequence maps each position's index, as a compacted
        annotation's unique values do. Label 0 is background and always written transparent.
    path : str or Path, optional
        Also write the table here.
    lateralized : bool
        Values are signed by hemisphere (see :mod:`.lateral`); names become ``<abbreviation>_left`` or ``_right``.

    Returns
    -------
    str
        The table's text.
    """
    mapping = labels if isinstance(labels, Mapping) else dict(enumerate(labels))
    lines = ["# label structure R G B A", "0 background 0 0 0 0"]
    for label in sorted(mapping):
        if label == 0:
            continue
        value = int(mapping[label])
        if lateralized:
            term, side = lateral.term_and_side(terminology, value)
            name = f"{term.abbreviation} {side}"
        else:
            term = terminology.by_value(value)
            name = term.abbreviation
        # Slicer splits each line on whitespace and shows underscores as spaces
        r, g, b = term.rgb
        lines.append(f"{label} {name.replace(' ', '_')} {r} {g} {b} 255")
    text = "\n".join(lines) + "\n"
    if path is not None:
        Path(path).write_text(text, encoding="utf-8")
    return text
