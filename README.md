# AIND atlas terminology

![CI](https://github.com/AllenNeuralDynamics/aind-atlas-terminology/actions/workflows/ci-call.yml/badge.svg)
[![semantic-release: angular](https://img.shields.io/badge/semantic--release-angular-e10079?logo=semantic-release)](https://github.com/semantic-release/semantic-release)
[![License](https://img.shields.io/badge/license-MIT-brightgreen)](LICENSE)
[![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border.json)](https://github.com/copier-org/copier)

Resolve and select brain structures in Allen atlas-assets terminologies

## Installation

If you choose to clone the repository, you can install the package by running the following command from the root directory of the repository:

```bash
pip install .
```

## Usage

A terminology is the tree of structures an atlas's annotation volumes label, in the
[atlas-assets](https://atlas-assets.readthedocs.io) format Allen publishes to the public
`allen-atlas-assets` bucket. The package has no dependencies and never touches the network: the
Allen adult mouse releases 2017 (which labels the CCFv3 2017 annotation), 2020, 2026-03 and 2026
ship with it (`BUNDLED`), pinned by checksum. Any other release loads with
`from_directory(path)`.

```python
from aind_atlas_terminology import load, lateral, slicer_color_table

ccf = load()  # allen-adult-mouse-terminology 2017
ccf26 = load("2026")

# A structure is named by abbreviation, full name or identifier
ccf.term("LGd")  # Term(identifier='MBA:170', ...)
ccf.term("dorsal part of the lateral geniculate complex")
ccf.resolve("CUL4 5").matched_on  # 'alias': the IBL spelling of 'CUL4, 5'
ccf.term("LGd-c")  # StructureNotFoundError: ... did you mean LGd-co (...)?
ccf26.term("LH")  # AmbiguousStructureError: MBA:186 (Lateral habenula), MBA:1968 (Left hemisphere)
ccf.terms_for(["LGd", "TH", "CA1"])  # reports every failure at once
ccf.search("geniculate")

# Annotation values belong to a release, so they have their own lookup
ccf.by_value(170)  # LGd; in 2026, LGd is 1635
ccf.get("MBA:170")  # identifiers are stable across releases

# Subtrees
ccf.children("LGd")  # LGd-sh, LGd-co, LGd-ip
ccf.ancestors("LGd")  # root, grey, BS, IB, TH, DORsm, GENd
ccf.ancestor_at("LGd-co", 4)  # TH
ccf.partition("TH", 6)  # tiles the thalamus at depth 6
ccf.annotation_values("LGd")  # {170, 496345664, 496345668, 496345672}
ccf.values_present("LGd", np.unique(annotation))
ccf.in_order(["CB", "LGd", "CA1"])  # anatomical order

# Tables: plain dicts, which pandas, polars and pyarrow all read
pd.DataFrame(ccf.to_records())  # brainglobe's lookup_df columns, plus depth

# Hemispheres are a convention of some annotation volumes, not of the terminology:
# iblatlas and the compacted lateralized CCF negate left-hemisphere values
lateral.term_and_side(ccf, -496345668)  # (Term(... 'LGd-co' ...), 'left')
lateral.values_present(ccf, "LGd", np.unique(annotation), "left")
slicer_color_table(ccf, compact_values, "ccf.ctbl", lateralized=True)
```

Where a structure is named, an int is refused, since it could mean an identifier or a
release's annotation value; brainglobe treats them as one number, which holds in 2017 and
nowhere since. Releases since 2020 have several roots, and only 2017 publishes Allen's
sibling order (`has_sibling_order`); elsewhere siblings keep the table's order.

Allen rewrites published files in place, so the vendored files are pinned in
`src/aind_atlas_terminology/data/sources.json` with their sha256, ETag and modification time.
`uv run python scripts/update_terminologies.py` re-downloads them and lists what changed;
`... update_terminologies.py allen-adult-mouse-terminology <version>` adds a release. A change to
the data is a commit and a release of this package.

The bundled terminology data are © Allen Institute, CC-BY-4.0.

## Contributing

Setup, checks, tests and conventions are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
