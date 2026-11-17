"""Load terminology releases: vendored in the package, or from a directory.

A release directory holds ``manifest.json`` (its name and version) and ``terminology.csv``, laid out as the
atlas-assets specification describes. The vendored releases are pinned by checksum in ``data/sources.json``, since
Allen rewrites published files in place; ``scripts/update_terminologies.py`` refreshes them.
"""

from __future__ import annotations

import csv
import json
from importlib import resources
from pathlib import Path

from aind_atlas_terminology.term import Term
from aind_atlas_terminology.terminology import Terminology

ALLEN_MOUSE = "allen-adult-mouse-terminology"

_DATA = resources.files("aind_atlas_terminology") / "data"

BUNDLED: dict[str, tuple[str, ...]] = {
    name: tuple(versions) for name, versions in json.loads((_DATA / "sources.json").read_text("utf-8")).items()
}
"""Vendored releases: terminology name -> versions."""

# The IBL / structure_tree_safe_2017 copy of the Allen ontology spells these differently from Allen.
ALLEN_MOUSE_ALIASES = {
    "CUL4 5": "CUL4, 5",
    "CUL4 5gr": "CUL4, 5gr",
    "CUL4 5mo": "CUL4, 5mo",
    "CUL4 5pu": "CUL4, 5pu",
    "Mmme": "MMme",
    "Mml": "MMl",
    "Mmm": "MMm",
    "Mmp": "MMp",
    "Mmd": "MMd",
}

_LEGACY_STRUCTURES = "legacy_files/adult_mouse_ccf_structures.csv"


def load(version: str = "2017", name: str = ALLEN_MOUSE) -> Terminology:
    """Load a vendored release; see :data:`BUNDLED`. Other releases load with :func:`from_directory`."""
    if version not in BUNDLED.get(name, ()):
        vendored = "; ".join(f"{n} {', '.join(v)}" for n, v in BUNDLED.items())
        raise LookupError(
            f"{name} {version} is not vendored (vendored: {vendored}); "
            "download it and use from_directory, or add it with scripts/update_terminologies.py"
        )
    with resources.as_file(_DATA / name / version) as path:
        return from_directory(path)


def from_directory(path: str | Path) -> Terminology:
    """Read a release directory.

    An Allen adult mouse release also gets the IBL spellings as aliases and, where its legacy structures table is
    present (2017 only), Allen's sibling order.
    """
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    name, version = manifest["name"], str(manifest["version"])
    with open(path / "terminology.csv", newline="", encoding="utf-8") as fh:
        terms = [_term(row) for row in csv.DictReader(fh)]
    aliases: dict[str, str] = {}
    order = None
    if name == ALLEN_MOUSE:
        abbreviations = {t.abbreviation for t in terms}
        aliases = {a: c for a, c in ALLEN_MOUSE_ALIASES.items() if c in abbreviations}
        legacy = path / _LEGACY_STRUCTURES
        if legacy.exists():
            with open(legacy, newline="", encoding="utf-8") as fh:
                order = {f"MBA:{r['id']}": int(r["graph_order"]) for r in csv.DictReader(fh)}
    return Terminology(terms, name=name, version=version, aliases=aliases, order=order)


def _term(row: dict[str, str]) -> Term:
    """Build a term from one ``terminology.csv`` row."""
    value = row.get("annotation_value", "").strip()
    color = row.get("color_hex_triplet", "").strip().lstrip("#")
    return Term(
        identifier=row["identifier"].strip(),
        parent_identifier=row.get("parent_identifier", "").strip() or None,
        annotation_value=int(float(value)) if value else None,
        name=row["name"].strip(),
        abbreviation=row["abbreviation"].strip(),
        # some tables drop leading zeros
        color="#" + color.zfill(6).upper() if color else "#808080",
    )
