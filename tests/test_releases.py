"""Tests for loading releases and the bundled data."""

import io
import json
import urllib.error
import urllib.request

import pytest

from aind_atlas_terminology import from_directory, load


def write_release(path, rows, name="toy", version="1"):
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(json.dumps({"name": name, "version": version}))
    header = "identifier,annotation_value,parent_identifier,name,abbreviation,color_hex_triplet\n"
    (path / "terminology.csv").write_text(header + "".join(",".join(r) + "\n" for r in rows))
    return path


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


def test_bundled_has_sibling_order_and_every_alias():
    terms = load()
    assert terms.has_sibling_order
    assert len(terms.aliases) == 9


def fake_bucket(monkeypatch, root, missing=()):
    """Serve files under ``root`` as the bucket; record requests."""
    requested = []

    def urlopen(url, timeout):
        requested.append(url)
        rel = url.split("/terminologies/", 1)[1]
        if rel.endswith(missing) or not (root / rel).exists():
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return io.BytesIO((root / rel).read_bytes())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return requested


def test_load_downloads_once_and_remembers_missing_legacy_file(tmp_path, monkeypatch):
    name = "allen-adult-mouse-terminology"
    write_release(tmp_path / "bucket" / name / "2020", [("MBA:997", "997", "", "root", "root", "")], name=name)
    requested = fake_bucket(monkeypatch, tmp_path / "bucket")
    for _ in range(2):
        terms = load("2020", cache_dir=tmp_path / "cache", remote="https://bucket")
        assert terms.version == "1" and not terms.has_sibling_order
    assert len(requested) == 3


def test_load_unknown_release_names_known_ones(tmp_path, monkeypatch):
    fake_bucket(monkeypatch, tmp_path)
    with pytest.raises(LookupError, match="known releases: 2017, 2020"):
        load("1999", cache_dir=tmp_path / "cache")
    assert not list((tmp_path / "cache").rglob("*.part"))
