"""Signed values in lateralized annotation volumes.

Terminologies have no hemispheres. Some annotation volumes (iblatlas's, and the compacted lateralized CCF these
packages share) mark the left hemisphere by negating a structure's annotation value; this module decodes that
convention and nothing else.
"""

from __future__ import annotations

from aind_atlas_terminology.term import Hemisphere, Term
from aind_atlas_terminology.terminology import Terminology


def split(value: int) -> tuple[int, Hemisphere]:
    """Split a signed value into its annotation value and hemisphere; 0 is background and raises ``ValueError``."""
    value = int(value)
    if value == 0:
        raise ValueError("0 is background, in neither hemisphere")
    return abs(value), "left" if value < 0 else "right"


def signed(value: int, hemisphere: Hemisphere) -> int:
    """Return the value a lateralized volume uses for ``value`` in ``hemisphere``."""
    return -abs(value) if hemisphere == "left" else abs(value)


def term_and_side(terminology: Terminology, value: int) -> tuple[Term, Hemisphere]:
    """Return the term and hemisphere a signed value labels."""
    magnitude, side = split(value)
    return terminology.by_value(magnitude), side


def values_present(
    terminology: Terminology, query: str | Term, present: list[int] | set[int], hemisphere: Hemisphere | None = None
) -> list[int]:
    """Return the signed values under ``query`` that occur in ``present``, optionally in one hemisphere only.

    Raises ``LookupError`` if none occur.
    """
    wanted = terminology.annotation_values(query)
    found = sorted(
        v
        for v in {int(p) for p in present}
        if v != 0 and abs(v) in wanted and (hemisphere is None or split(v)[1] == hemisphere)
    )
    if not found:
        term = terminology.term(query)
        side = f" in the {hemisphere} hemisphere" if hemisphere else ""
        raise LookupError(f"no voxel of the annotation is in {term.abbreviation} or beneath it{side}")
    return found
