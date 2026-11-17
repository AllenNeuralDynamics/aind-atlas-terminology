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
`allen-atlas-assets` bucket. The 2017 Allen adult mouse terminology, which labels the CCFv3 2017
annotation, ships with the package; other releases download once into `~/.cache`.

```python
from aind_atlas_terminology import Terminology, slicer_color_table

ccf = Terminology.bundled()  # allen-adult-mouse-terminology 2017
ccf2026 = Terminology.fetch("allen-adult-mouse-terminology", "2026")

# A user may name a structure by abbreviation, full name, identifier or annotation value
ccf.term("LGd")                                    # Term(identifier='MBA:170', ...)
ccf.term("dorsal part of the lateral geniculate complex")
ccf.resolve("CUL4 5").matched_on                   # 'alias': the IBL spelling of 'CUL4, 5'
ccf.term("LGd-c")                                  # LookupError: ... did you mean LGd-co (...)?
ccf.search("geniculate")                           # substring search, exact abbreviations first

# Subtrees
ccf.children("LGd")                                # LGd-sh, LGd-co, LGd-ip
ccf.ancestors("LGd")                               # root, grey, BS, IB, TH, ...
ccf.annotation_values("LGd")                       # {170, 496345664, 496345668, 496345672}
ccf.values_present("LGd", np.unique(annotation))   # the subtree's values that a volume uses

# Lateralized annotations (negative = left)
ccf.lateral(-496345668)                            # (Term(... 'LGd-co' ...), 'left')
slicer_color_table(ccf, {i: v for i, v in enumerate(values)}, "ccf.ctbl", lateralized=True)
```

An annotation value belongs to its release: 2017 labels LGd 170, 2020 labels it 165, and 2026 labels
it 1635. Identifiers (`MBA:170`) are stable across releases.

Releases since 2020 have several roots (`brain`, `unassigned`, and in 2026-03 the midline). Only
the 2017 release publishes Allen's sibling order (`graph_order`); for the others, siblings keep the
order of the table.

The bundled terminology data are © Allen Institute, CC-BY-4.0.

## Contributing

Setup, checks, tests and conventions are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
