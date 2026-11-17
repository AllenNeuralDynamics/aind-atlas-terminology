"""A terminology's structures, and the outcome of resolving a user's name for one."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MatchKind = Literal["identifier", "abbreviation", "alias", "abbreviation_ci", "name_ci"]
Hemisphere = Literal["left", "right"]


@dataclass(frozen=True, slots=True)
class Term:
    """One structure of a terminology."""

    identifier: str
    """Stable across releases, e.g. ``MBA:170``."""
    parent_identifier: str | None
    annotation_value: int | None
    """Value labeling the structure in this release's annotation volumes; releases renumber, so it is not an id."""
    name: str
    abbreviation: str
    color: str
    """Display color, ``#RRGGBB``."""

    @property
    def rgb(self) -> tuple[int, int, int]:
        """Return the color as 0-255 integers."""
        r, g, b = bytes.fromhex(self.color[1:])
        return r, g, b


StructureRef = str | Term
"""A structure as a caller names it: an identifier, abbreviation, alias or full name, or a :class:`Term`."""


@dataclass(frozen=True, slots=True)
class Match:
    """The terms a query resolved to under the first rule that matched any; empty when none did."""

    query: str
    terms: tuple[Term, ...]
    matched_on: MatchKind | None

    @property
    def term(self) -> Term | None:
        """Return the matched term when exactly one matched."""
        return self.terms[0] if len(self.terms) == 1 else None

    @property
    def ambiguous(self) -> bool:
        """Report whether several terms matched equally well."""
        return len(self.terms) > 1


class StructureNotFoundError(LookupError):
    """No structure matches the query."""

    def __init__(self, message: str, suggestions: list[Term]) -> None:
        super().__init__(message)
        self.suggestions = suggestions


class AmbiguousStructureError(LookupError):
    """Several structures match the query equally well; name one by identifier."""

    def __init__(self, message: str, candidates: tuple[Term, ...]) -> None:
        super().__init__(message)
        self.candidates = candidates
