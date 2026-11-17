"""Tests for loading, resolving and tree queries."""

import io
import json
import urllib.error
import urllib.request

import pytest

from aind_atlas_terminology import Term, Terminology, slicer_color_table

LGD_LEAVES = {496345664, 496345668, 496345672}


@pytest.fixture(scope="module")
def ccf():
    return Terminology.bundled()


def test_bundled_release(ccf):
    assert ccf.name == "allen-adult-mouse-terminology"
    assert ccf.version == "2017"
    assert len(ccf) == 1327
    assert [t.abbreviation for t in ccf.roots] == ["root"]


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ("MBA:170", "identifier"),
        (170, "annotation_value"),
        ("LGd", "abbreviation"),
        ("lgd", "abbreviation_ci"),
        ("dorsal part of the lateral geniculate complex", "name_ci"),
    ],
)
def test_resolve(ccf, query, kind):
    match = ccf.resolve(query)
    assert match.term is not None
    assert match.term.abbreviation == "LGd"
    assert match.matched_on == kind


def test_ibl_spellings_resolve_as_aliases(ccf):
    for ibl, allen in [("CUL4 5", "CUL4, 5"), ("Mmme", "MMme")]:
        match = ccf.resolve(ibl)
        assert match.matched_on == "alias"
        assert match.term is not None and match.term.abbreviation == allen


def test_unknown_lists_candidates(ccf):
    assert ccf.resolve("nowhere").term is None
    with pytest.raises(LookupError, match="LGd-co"):
        ccf.term("LGd-c")


def test_search_ranks_exact_abbreviation_first(ccf):
    hits = ccf.search("LGd")
    assert hits[0].abbreviation == "LGd"
    assert {t.abbreviation for t in hits[1:4]} == {"LGd-co", "LGd-sh", "LGd-ip"}


def test_tree(ccf):
    assert ccf.parent("root") is None
    assert [t.abbreviation for t in ccf.ancestors("LGd")][:2] == ["root", "grey"]
    assert ccf.ancestors("LGd", include_self=True)[-1].abbreviation == "LGd"
    assert ccf.depth("root") == 0
    assert {t.abbreviation for t in ccf.children("LGd")} == {"LGd-co", "LGd-sh", "LGd-ip"}
    assert ccf.descendants("LGd")[0].abbreviation == "LGd"
    assert len(ccf.descendants("root")) == len(ccf)


def test_iteration_is_preorder(ccf):
    seen: set[str] = set()
    for term in ccf:
        assert term.parent_identifier is None or term.parent_identifier in seen
        seen.add(term.identifier)


def test_subtrees_are_contiguous_in_order(ccf):
    order = [t.identifier for t in ccf]
    subtree = [t.identifier for t in ccf.descendants("TH")]
    start = order.index(subtree[0])
    assert order[start : start + len(subtree)] == subtree


def test_sibling_order_follows_graph_order(ccf):
    # Allen lists the cerebrum before the brain stem and cerebellum
    assert [t.abbreviation for t in ccf.children("grey")] == ["CH", "BS", "CB"]


def test_annotation_values(ccf):
    assert ccf.annotation_values("LGd") == LGD_LEAVES | {170}


def test_values_present_keeps_sign(ccf):
    present = [0, 171, -496345664, 496345668, 12345]
    assert ccf.values_present("LGd", present) == [-496345664, 496345668]
    with pytest.raises(LookupError):
        ccf.values_present("LGd", [0, 1])


def test_lateral(ccf):
    assert ccf.lateral(-170) == (ccf.get(170), "left")
    assert ccf.lateral(170) == (ccf.get(170), "right")
    with pytest.raises(KeyError):
        ccf.lateral(0)


def test_get(ccf):
    assert ccf.get("MBA:170") is ccf.get(170)
    with pytest.raises(KeyError):
        ccf.get("MBA:0")


def test_slicer_color_table(ccf, tmp_path):
    path = tmp_path / "t.ctbl"
    text = slicer_color_table(ccf, {0: 0, 1: -496345668, 2: 1091}, path, lateralized=True)
    lines = text.splitlines()
    assert lines[1] == "0 background 0 0 0 0"
    r, g, b = bytes.fromhex(ccf.get(496345668).color[1:])
    assert lines[2] == f"1 LGd-co_left {r} {g} {b} 255"
    assert lines[3].startswith("2 CUL4,_5_right ")
    assert path.read_text() == text


def _write(tmp_path, rows, name="toy"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifest.json").write_text(json.dumps({"name": name, "version": "1"}))
    header = "identifier,annotation_value,parent_identifier,name,abbreviation,color_hex_triplet\n"
    (tmp_path / "terminology.csv").write_text(header + "".join(",".join(r) + "\n" for r in rows))
    return tmp_path


def test_from_directory_without_order(tmp_path):
    rows = [
        ("A:1", "1", "", "root", "r", "#FFFFFF"),
        ("A:3", "", "A:1", "Bee", "b", "abc"),
        ("A:2", "2", "A:1", "Ay", "a", ""),
    ]
    terms = Terminology.from_directory(_write(tmp_path, rows))
    assert terms.version == "1" and terms.aliases == {}
    assert [t.abbreviation for t in terms] == ["r", "b", "a"]
    assert terms.get("A:3") == Term("A:3", "A:1", None, "Bee", "b", "#000ABC")
    assert terms.get("A:2").color == "#808080"
    assert terms.annotation_values("r") == {1, 2}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([("A:1", "1", "", "r", "r", ""), ("A:1", "2", "", "s", "s", "")], "appears twice"),
        ([("A:1", "1", "", "r", "r", ""), ("A:2", "1", "A:1", "s", "s", "")], "appears twice"),
        ([("A:1", "1", "", "r", "r", ""), ("A:2", "2", "A:9", "s", "s", "")], "unknown parent"),
        ([("A:1", "1", "A:2", "r", "r", ""), ("A:2", "2", "A:1", "s", "s", "")], "no root"),
        (
            [("A:1", "1", "", "r", "r", ""), ("A:2", "2", "A:3", "s", "s", ""), ("A:3", "3", "A:2", "t", "t", "")],
            "reachable",
        ),
    ],
)
def test_malformed(tmp_path, rows, message):
    with pytest.raises(ValueError, match=message):
        Terminology.from_directory(_write(tmp_path, rows))


def test_unbundled_release_refused():
    with pytest.raises(LookupError, match="fetch"):
        Terminology.bundled(version="2020")


def test_fetch_uses_cache(tmp_path):
    rows = [("A:1", "1", "", "root", "r", "")]
    local = tmp_path / "toy" / "1"
    local.mkdir(parents=True)
    _write(local, rows)
    terms = Terminology.fetch("toy", "1", cache_dir=tmp_path, remote="http://invalid.invalid")
    assert terms.roots[0].abbreviation == "r"


def test_several_roots(tmp_path):
    rows = [
        ("A:1", "1", "", "brain", "b", ""),
        ("A:0", "0", "", "unassigned", "u", ""),
        ("A:2", "2", "A:1", "x", "x", ""),
    ]
    terms = Terminology.from_directory(_write(tmp_path, rows))
    assert [t.abbreviation for t in terms.roots] == ["b", "u"]
    assert [t.abbreviation for t in terms] == ["b", "x", "u"]
    assert terms.depth("x") == 1


def test_fetch_skips_missing_legacy_file(tmp_path, monkeypatch):
    src = _write(tmp_path / "src", [("MBA:997", "997", "", "root", "root", "")], name="allen-adult-mouse-terminology")
    requested: list[str] = []

    def fake_urlopen(url, timeout):
        requested.append(url)
        rel = url.split("/2020/", 1)[1]
        if rel.startswith("legacy_files/"):
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return io.BytesIO((src / rel).read_bytes())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    for _ in range(2):
        terms = Terminology.fetch("allen-adult-mouse-terminology", "2020", cache_dir=tmp_path / "cache")
        assert terms.order is None and terms.aliases
    assert len(requested) == 3
