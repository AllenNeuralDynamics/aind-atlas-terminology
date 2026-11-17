"""Resolve and select brain structures in Allen atlas-assets terminologies."""

from importlib.metadata import PackageNotFoundError, version

from aind_atlas_terminology.export import slicer_color_table
from aind_atlas_terminology.terminology import BUNDLED, DEFAULT_REMOTE, Match, Term, Terminology

try:
    __version__ = version("aind-atlas-terminology")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"

__all__ = ["BUNDLED", "DEFAULT_REMOTE", "Match", "Term", "Terminology", "__version__", "slicer_color_table"]
