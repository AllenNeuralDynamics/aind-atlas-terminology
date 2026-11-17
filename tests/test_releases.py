"""Tests for loading releases and the vendored data."""

import hashlib
import json
from importlib import resources

import pytest

from aind_atlas_terminology import BUNDLED, from_directory, load

DATA = resources.files("aind_atlas_terminology") / "data"


def write_release(path, rows, name="toy", version="1"):
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    header = "identifier,annotation_value,parent_identifier,name,abbreviation,color_hex_triplet\n"
    (path / "terminology.csv").write_text(header + "".join(",".join(r) + "\n" for r in rows), encoding="utf-8")
    return path


def vendored_files():
    sources = json.loads((DATA / "sources.json").read_text("utf-8"))
    return [
        (name, version, rel, pin["sha256"])
        for name, versions in sources.items()
        for version, files in versions.items()
        for rel, pin in files.items()
    ]


@pytest.mark.parametrize(("name", "version", "rel", "sha256"), vendored_files())
def test_vendored_files_match_their_pins(name, version, rel, sha256):
    assert hashlib.sha256((DATA / name / version / rel).read_bytes()).hexdigest() == sha256


@pytest.mark.parametrize(("name", "version"), [(n, v) for n, vs in BUNDLED.items() for v in vs])
def test_every_vendored_release_loads(name, version):
    terms = load(version, name)
    assert (terms.name, terms.version) == (name, version)
    assert terms.term("LGd").identifier == "MBA:170"
    assert len(terms.aliases) == 9


def test_release_differences():
    assert load("2017").has_sibling_order and not load("2026").has_sibling_order
    assert [t.abbreviation for t in load("2026").roots] == ["brain", "unassigned"]
    assert [load(v).term("LGd").annotation_value for v in ("2017", "2020", "2026")] == [170, 165, 1635]


def test_unvendored_release_points_to_from_directory():
    with pytest.raises(LookupError, match="from_directory"):
        load("1999")


def test_from_directory_parses_rows(tmp_path):
    rows = [
        ("A:1", "1", "", "root", "r", "#ffffff"),
        ("A:3", "", "A:1", "Bee", "b", "abc"),
        ("A:2", "2", "A:1", "Ay", "a", ""),
    ]
    terms = from_directory(write_release(tmp_path, rows))
    assert (terms.name, terms.version, terms.aliases) == ("toy", "1", {})
    assert [t.abbreviation for t in terms] == ["r", "b", "a"]
    bee = terms.get("A:3")
    assert (bee.annotation_value, bee.color, bee.rgb) == (None, "#000ABC", (0, 10, 188))
    assert terms.get("A:2").color == "#808080"
    assert terms.annotation_values("r") == {1, 2}


def test_allen_aliases_only_where_the_release_has_the_target(tmp_path):
    rows = [("MBA:997", "997", "", "root", "root", ""), ("MBA:732", "732", "MBA:997", "Medial", "MMme", "")]
    terms = from_directory(write_release(tmp_path, rows, name="allen-adult-mouse-terminology"))
    assert terms.aliases == {"Mmme": "MMme"}
    assert not terms.has_sibling_order
