"""Resolve and select brain structures in Allen atlas-assets terminologies."""

from importlib.metadata import PackageNotFoundError, version

from aind_atlas_terminology import lateral
from aind_atlas_terminology.export import slicer_color_table
from aind_atlas_terminology.releases import BUNDLED, DEFAULT_REMOTE, KNOWN_RELEASES, from_directory, load
from aind_atlas_terminology.term import (
    AmbiguousStructureError,
    Hemisphere,
    Match,
    StructureNotFoundError,
    StructureRef,
    Term,
)
from aind_atlas_terminology.terminology import Terminology

try:
    __version__ = version("aind-atlas-terminology")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = [
    "BUNDLED",
    "DEFAULT_REMOTE",
    "KNOWN_RELEASES",
    "AmbiguousStructureError",
    "Hemisphere",
    "Match",
    "StructureNotFoundError",
    "StructureRef",
    "Term",
    "Terminology",
    "__version__",
    "from_directory",
    "lateral",
    "load",
    "slicer_color_table",
]
