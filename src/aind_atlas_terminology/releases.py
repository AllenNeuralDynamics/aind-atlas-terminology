"""Load terminology releases: bundled, cached from the public bucket, or from a directory.

A release directory holds ``manifest.json`` (its name and version) and ``terminology.csv``, laid out as the
atlas-assets specification describes.
"""

from __future__ import annotations

import csv
import json
import shutil
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path

from aind_atlas_terminology.term import Term
from aind_atlas_terminology.terminology import Terminology

ALLEN_MOUSE = "allen-adult-mouse-terminology"

DEFAULT_REMOTE = "https://allen-atlas-assets.s3.amazonaws.com"
"""Public bucket holding Allen's atlas assets."""

BUNDLED = ((ALLEN_MOUSE, "2017"),)
"""Releases shipped with the package, as ``(name, version)``."""

KNOWN_RELEASES = {ALLEN_MOUSE: ("2017", "2020", "2026-03", "2026")}
"""Releases :func:`load` can fetch, checked against the bucket; it tries any other version it is asked for."""

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


def load(
    version: str = "2017",
    name: str = ALLEN_MOUSE,
    *,
    cache_dir: str | Path | None = None,
    remote: str = DEFAULT_REMOTE,
) -> Terminology:
    """Load a release: from the package if bundled, otherwise downloaded once into ``cache_dir``.

    The default cache is ``~/.cache/aind-atlas-terminology``.
    """
    if (name, version) in BUNDLED:
        with resources.as_file(resources.files("aind_atlas_terminology") / "data" / name / version) as path:
            return from_directory(path)
    cache = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "aind-atlas-terminology"
    local = cache / name / version
    _download(f"{remote.rstrip('/')}/terminologies/{name}/{version}", local, name, version)
    return from_directory(local)


def from_directory(path: str | Path) -> Terminology:
    """Read a release directory.

    An Allen adult mouse release also gets the IBL spellings as aliases and, where its legacy structures table is
    present (2017 only), Allen's sibling order.
    """
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text())
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


def _download(base_url: str, local: Path, name: str, version: str) -> None:
    """Fetch a release's files that are not yet cached; a missing optional file is remembered, not retried."""
    files = ["manifest.json", "terminology.csv"] + ([_LEGACY_STRUCTURES] if name == ALLEN_MOUSE else [])
    for rel in files:
        target = local / rel
        absent = target.with_suffix(".absent")
        if target.exists() or absent.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        try:
            with urllib.request.urlopen(f"{base_url}/{rel}", timeout=60) as resp, open(partial, "wb") as out:
                shutil.copyfileobj(resp, out)
        except urllib.error.HTTPError as err:
            partial.unlink(missing_ok=True)
            if err.code == 404 and rel == _LEGACY_STRUCTURES:
                absent.touch()
                continue
            if err.code in (403, 404):  # S3 answers 403 for a missing key in a bucket that refuses listing
                known = KNOWN_RELEASES.get(name)
                hint = f"; known releases: {', '.join(known)}" if known else ""
                raise LookupError(f"no release {name} {version} at {base_url}{hint}") from err
            raise
        except OSError:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(target)


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
