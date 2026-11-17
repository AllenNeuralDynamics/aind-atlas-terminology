"""Tests for lookup, resolution and tree queries."""

import pytest

from aind_atlas_terminology import (
    AmbiguousStructureError,
    StructureNotFoundError,
    Term,
    Terminology,
    load,
)

LGD_LEAVES = {496345664, 496345668, 496345672}


@pytest.fixture(scope="module")
def ccf():
    return load()


def toy(rows, **kwargs):
    """Build a terminology from (identifier, parent, value, abbreviation) rows."""
    terms = [Term(i, p, v, a.upper() + " name", a, "#000000") for i, p, v, a in rows]
    return Terminology(terms, **kwargs)


def test_bundled_release(ccf):
    assert (ccf.name, ccf.version, len(ccf)) == ("allen-adult-mouse-terminology", "2017", 1327)
    assert [t.abbreviation for t in ccf.roots] == ["root"]
    assert ccf.has_sibling_order
    assert "2017" in repr(ccf)


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ("MBA:170", "identifier"),
        ("LGd", "abbreviation"),
        (" lgd ", "abbreviation_ci"),
        ("dorsal part of the lateral geniculate complex", "name_ci"),
    ],
)
def test_resolve(ccf, query, kind):
    match = ccf.resolve(query)
    assert match.term is not None and match.term.abbreviation == "LGd"
    assert match.matched_on == kind and not match.ambiguous


def test_ibl_spellings_resolve_as_aliases(ccf):
    for ibl, allen in [("CUL4 5", "CUL4, 5"), ("Mmme", "MMme")]:
        match = ccf.resolve(ibl)
        assert match.matched_on == "alias"
        assert match.term is not None and match.term.abbreviation == allen


def test_exact_case_wins_over_case_insensitive(ccf):
    assert ccf.term("cm").name == "cranial nerves"
    assert ccf.term("CM").name == "Central medial nucleus of the thalamus"


def test_case_insensitive_collision_is_ambiguous(ccf):
    with pytest.raises(AmbiguousStructureError, match="MBA:599") as err:
        ccf.term("Cm")
    assert {t.identifier for t in err.value.candidates} == {"MBA:599", "MBA:967"}


def test_repeated_abbreviation_is_ambiguous():
    terms = toy([("A:1", None, 1, "brain"), ("A:2", "A:1", 2, "LH"), ("A:3", "A:1", 3, "LH")])
    assert terms.resolve("LH").ambiguous
    with pytest.raises(AmbiguousStructureError):
        terms.term("LH")
    assert terms.term("A:3").identifier == "A:3"


def test_unknown_suggests(ccf):
    assert ccf.resolve("nowhere").terms == ()
    with pytest.raises(StructureNotFoundError, match="LGd-co") as err:
        ccf.term("LGd-c")
    assert err.value.suggestions


def test_ints_are_refused_as_names(ccf):
    with pytest.raises(TypeError, match="by_value"):
        ccf.term(170)
    with pytest.raises(TypeError, match="by_value"):
        ccf.get(170)
    assert ccf.by_value(170) is ccf.get("MBA:170")
    with pytest.raises(KeyError):
        ccf.by_value(-1)


def test_term_from_another_release_is_refused(ccf):
    stranger = Term("MBA:170", None, 1, "x", "x", "#000000")
    with pytest.raises(StructureNotFoundError):
        ccf.term(stranger)
    assert ccf.term(ccf.get("MBA:170")).abbreviation == "LGd"


def test_terms_for_reports_every_failure(ccf):
    assert [t.abbreviation for t in ccf.terms_for(["LGd", "TH"])] == ["LGd", "TH"]
    with pytest.raises(LookupError, match="nowhere.*Cm"):
        ccf.terms_for(["nowhere", "LGd", "Cm"])


def test_search_ranks_exact_abbreviation_first(ccf):
    hits = ccf.search("LGd")
    assert hits[0].abbreviation == "LGd"
    assert {t.abbreviation for t in hits[1:4]} == {"LGd-co", "LGd-sh", "LGd-ip"}
    assert ccf.search("  ") == []
    assert len(ccf.search("a", limit=3)) == 3


def test_tree(ccf):
    assert ccf.parent("root") is None
    assert [t.abbreviation for t in ccf.ancestors("LGd")] == ["root", "grey", "BS", "IB", "TH", "DORsm", "GENd"]
    assert ccf.ancestors("LGd", include_self=True)[-1].abbreviation == "LGd"
    assert ccf.depth("root") == 0 and ccf.depth("LGd") == 7
    assert [t.abbreviation for t in ccf.children("LGd")] == ["LGd-sh", "LGd-co", "LGd-ip"]
    assert ccf.is_leaf("LGd-co") and not ccf.is_leaf("LGd")
    assert [t.abbreviation for t in ccf.descendants("LGd", include_self=False)] == ["LGd-sh", "LGd-co", "LGd-ip"]
    assert len(ccf.descendants("root")) == len(ccf)


def test_iteration_is_preorder_and_subtrees_contiguous(ccf):
    order = [t.identifier for t in ccf]
    position = {identifier: i for i, identifier in enumerate(order)}
    assert all(t.parent_identifier is None or position[t.parent_identifier] < position[t.identifier] for t in ccf)
    subtree = [t.identifier for t in ccf.descendants("TH")]
    start = order.index(subtree[0])
    assert order[start : start + len(subtree)] == subtree


def test_sibling_order_follows_graph_order(ccf):
    assert [t.abbreviation for t in ccf.children("grey")] == ["CH", "BS", "CB"]
    assert [t.abbreviation for t in ccf.in_order(["CB", "LGd", "CA1"])] == ["CA1", "LGd", "CB"]


def test_ancestor_at(ccf):
    assert ccf.ancestor_at("LGd-co", 4).abbreviation == "TH"
    assert ccf.ancestor_at("LGd-co", 0).abbreviation == "root"
    assert ccf.ancestor_at("TH", 9).abbreviation == "TH"


def test_partition_tiles_the_subtree():
    # r has children a and b; a has children c and d; b is a leaf above depth 2
    terms = toy([("r", None, 1, "r"), ("a", "r", 2, "a"), ("b", "r", 3, "b"), ("c", "a", 4, "c"), ("d", "a", 5, "d")])
    assert [t.identifier for t in terms.partition("r", 2)] == ["c", "d", "b"]
    assert [t.identifier for t in terms.partition("r", 1)] == ["a", "b"]
    assert terms.partition("a", 0) == []


def test_partition_covers_every_leaf_once(ccf):
    leaves = {t.identifier for t in ccf.descendants("TH") if ccf.is_leaf(t)}
    covered = [leaf.identifier for p in ccf.partition("TH", 6) for leaf in ccf.descendants(p) if ccf.is_leaf(leaf)]
    assert sorted(covered) == sorted(leaves)


def test_annotation_values(ccf):
    assert ccf.annotation_values("LGd") == LGD_LEAVES | {170}
    assert ccf.values_present("LGd", [0, 171, 496345664, 496345668, 12345]) == [496345664, 496345668]
    with pytest.raises(LookupError, match="2017"):
        ccf.values_present("LGd", [0, 1])


def test_records_carry_brainglobe_columns(ccf):
    records = ccf.to_records()
    lgd = next(r for r in records if r["abbreviation"] == "LGd")
    assert lgd["acronym"] == "LGd" and lgd["id"] == 170 and lgd["depth"] == 7
    assert lgd["structure_id_path"][0] == 997 and lgd["structure_id_path"][-1] == 170
    assert records[0]["abbreviation"] == "root"
    assert len(records) == len(ccf)


def test_several_roots_keep_table_order():
    terms = toy([("A:1", None, 1, "brain"), ("A:0", None, 0, "unassigned"), ("A:2", "A:1", 2, "x")])
    assert [t.abbreviation for t in terms.roots] == ["brain", "unassigned"]
    assert [t.abbreviation for t in terms] == ["brain", "x", "unassigned"]
    assert not terms.has_sibling_order


@pytest.mark.parametrize(
    ("rows", "kwargs", "message"),
    [
        ([("A:1", None, 1, "r"), ("A:1", None, 2, "s")], {}, "appears twice"),
        ([("A:1", None, 1, "r"), ("A:2", "A:1", 1, "s")], {}, "appears twice"),
        ([("A:1", None, 1, "r"), ("A:2", "A:9", 2, "s")], {}, "unknown parent"),
        ([("A:1", "A:2", 1, "r"), ("A:2", "A:1", 2, "s")], {}, "no root"),
        ([("A:1", None, 1, "r"), ("A:2", "A:3", 2, "s"), ("A:3", "A:2", 3, "t")], {}, "reachable"),
        ([("A:1", None, 1, "r")], {"aliases": {"R": "missing"}}, "aliases"),
    ],
)
def test_malformed(rows, kwargs, message):
    with pytest.raises(ValueError, match=message):
        toy(rows, **kwargs)
