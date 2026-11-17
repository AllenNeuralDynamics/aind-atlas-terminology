"""Write a terminology's names and colors in formats viewers read."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from aind_atlas_terminology.terminology import Terminology


def slicer_color_table(
    terminology: Terminology,
    labels: Mapping[int, int],
    path: str | Path | None = None,
    *,
    lateralized: bool = False,
) -> str:
    """Build a 3D Slicer color table (``.ctbl``) for a label volume.

    Parameters
    ----------
    terminology : Terminology
        Supplies names and colors.
    labels : mapping of int to int
        Label value in the volume -> annotation value it stands for; identity for an annotation volume, or a compact
        index -> value map for a compacted one. Label 0 is background and always written transparent.
    path : str or Path, optional
        Also write the table here.
    lateralized : bool
        Negative annotation values are the left hemisphere; names become ``<abbreviation> left`` or ``right``.

    Returns
    -------
    str
        The table's text.
    """
    lines = ["# label, structure, R G B A", "0 background 0 0 0 0"]
    for label in sorted(labels):
        if label == 0:
            continue
        value = int(labels[label])
        if lateralized:
            term, side = terminology.lateral(value)
            name = f"{term.abbreviation} {side}"
        else:
            term = terminology.get(value)
            name = term.abbreviation
        # Slicer splits each line on whitespace; it shows underscores as spaces
        name = name.replace(" ", "_")
        rgb = bytes.fromhex(term.color.lstrip("#"))
        lines.append(f"{label} {name} {rgb[0]} {rgb[1]} {rgb[2]} 255")
    text = "\n".join(lines) + "\n"
    if path is not None:
        Path(path).write_text(text)
    return text
