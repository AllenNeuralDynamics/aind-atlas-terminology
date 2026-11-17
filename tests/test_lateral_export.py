"""Tests for signed lateralized values and color tables."""

import pytest

from aind_atlas_terminology import lateral, load, slicer_color_table


@pytest.fixture(scope="module")
def ccf():
    return load()


def test_split_and_signed():
    assert lateral.split(-170) == (170, "left")
    assert lateral.split(170) == (170, "right")
    assert lateral.signed(170, "left") == -170 and lateral.signed(-170, "right") == 170
    with pytest.raises(ValueError, match="background"):
        lateral.split(0)


def test_term_and_side(ccf):
    assert lateral.term_and_side(ccf, -170) == (ccf.get("MBA:170"), "left")


def test_values_present(ccf):
    present = [0, -496345664, 496345668, -171, 12345]
    assert lateral.values_present(ccf, "LGd", present) == [-496345664, 496345668]
    assert lateral.values_present(ccf, "LGd", present, "left") == [-496345664]
    with pytest.raises(LookupError, match="right hemisphere"):
        lateral.values_present(ccf, "LGd", [-170], "right")


def test_slicer_color_table(ccf, tmp_path):
    path = tmp_path / "t.ctbl"
    text = slicer_color_table(ccf, [0, -496345668, 1091], path, lateralized=True)
    lines = text.splitlines()
    assert lines[1] == "0 background 0 0 0 0"
    r, g, b = ccf.by_value(496345668).rgb
    assert lines[2] == f"1 LGd-co_left {r} {g} {b} 255"
    assert lines[3].startswith("2 CUL4,_5_right ")
    assert path.read_text() == text


def test_slicer_color_table_unlateralized_mapping(ccf):
    lines = slicer_color_table(ccf, {7: 170}).splitlines()
    assert lines[2].startswith("7 LGd ")
