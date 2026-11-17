"""Look up structures in a terminology and walk its tree.

A terminology is the hierarchy of structures an atlas's annotation volumes label, as the atlas-assets specification
(https://atlas-assets.readthedocs.io) describes it. It has no notion of hemispheres; see :mod:`.lateral`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from aind_atlas_terminology.term import (
    AmbiguousStructureError,
    Match,
    MatchKind,
    StructureNotFoundError,
    StructureRef,
    Term,
)


class Terminology:
    """A terminology release, indexed for lookup and tree queries.

    Parameters
    ----------
    terms : iterable of Term
        Every structure. Terms without a parent are roots; Allen's releases since 2020 have several.
    name, version : str
        The release, as its manifest names it.
    aliases : mapping of str to str
        Alternative abbreviations, mapped to the canonical one.
    order : mapping of str to int, optional
        Sibling order by identifier (Allen's ``graph_order``); without it siblings keep their table order.
    """

    def __init__(
        self,
        terms: Iterable[Term],
        *,
        name: str = "",
        version: str = "",
        aliases: Mapping[str, str] | None = None,
        order: Mapping[str, int] | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.terms: tuple[Term, ...] = tuple(terms)
        self._by_id: dict[str, Term] = {}
        self._by_value: dict[int, Term] = {}
        for t in self.terms:
            if t.identifier in self._by_id:
                raise ValueError(f"identifier {t.identifier} appears twice")
            self._by_id[t.identifier] = t
            if t.annotation_value is not None:
                if t.annotation_value in self._by_value:
                    raise ValueError(f"annotation_value {t.annotation_value} appears twice")
                self._by_value[t.annotation_value] = t
        abbreviations = {t.abbreviation for t in self.terms}
        unknown = {a: c for a, c in (aliases or {}).items() if c not in abbreviations}
        if unknown:
            raise ValueError(f"aliases name abbreviations that are not in the terminology: {unknown}")
        self.aliases = dict(aliases or {})
        self.has_sibling_order = order is not None
        self._index_names()
        self._build_tree(order)

    def _index_names(self) -> None:
        """Map each spelling to every term it could mean; a release may reuse an abbreviation."""
        self._names: dict[MatchKind, dict[str, list[Term]]] = {
            kind: defaultdict(list) for kind in ("abbreviation", "abbreviation_ci", "name_ci")
        }
        for t in self.terms:
            self._names["abbreviation"][t.abbreviation].append(t)
            self._names["abbreviation_ci"][t.abbreviation.casefold()].append(t)
            self._names["name_ci"][t.name.casefold()].append(t)

    def _build_tree(self, order: Mapping[str, int] | None) -> None:
        """Link children to parents, order siblings, and rank terms in preorder."""
        self._children: dict[str, list[str]] = {t.identifier: [] for t in self.terms}
        roots = []
        for t in self.terms:
            if t.parent_identifier is None:
                roots.append(t.identifier)
            elif t.parent_identifier not in self._by_id:
                raise ValueError(f"{t.identifier} has unknown parent {t.parent_identifier}")
            else:
                self._children[t.parent_identifier].append(t.identifier)
        if not roots:
            raise ValueError("no root: every term has a parent")
        if order is not None:
            for siblings in [roots, *self._children.values()]:
                siblings.sort(key=lambda i: order.get(i, len(order)))
        self._roots = roots
        # sorting by preorder rank keeps every subtree contiguous
        self._rank: dict[str, int] = {}
        self._depth: dict[str, int] = {}
        stack = [(r, 0) for r in reversed(roots)]
        while stack:
            node, depth = stack.pop()
            self._rank[node] = len(self._rank)
            self._depth[node] = depth
            stack.extend((c, depth + 1) for c in reversed(self._children[node]))
        # a term on a parent cycle is never reached from a root
        if len(self._rank) != len(self.terms):
            raise ValueError("some terms are not reachable from a root")

    def __repr__(self) -> str:
        """Name the release."""
        return f"Terminology({self.name!r}, {self.version!r}, {len(self)} terms)"

    def __len__(self) -> int:
        """Count the terms."""
        return len(self.terms)

    def __iter__(self) -> Iterator[Term]:
        """Yield every term before its descendants, siblings in sibling order."""
        return iter(sorted(self.terms, key=self._rank_of))

    def _rank_of(self, term: Term) -> int:
        """Return a term's preorder rank."""
        return self._rank[term.identifier]

    # ------------------------------------------------------------------ exact lookup

    @property
    def roots(self) -> list[Term]:
        """Return the terms without a parent, in sibling order."""
        return [self._by_id[i] for i in self._roots]

    def get(self, identifier: str) -> Term:
        """Look up a term by identifier, e.g. ``"MBA:170"``; raise ``KeyError`` if absent."""
        if not isinstance(identifier, str):
            raise TypeError(f"get takes an identifier string; for an annotation value use by_value({identifier!r})")
        return self._by_id[identifier]

    def by_value(self, value: int) -> Term:
        """Look up the term an annotation value labels in this release; raise ``KeyError`` if none does."""
        return self._by_value[int(value)]

    # ------------------------------------------------------------------ resolving names

    def resolve(self, query: str) -> Match:
        """Find the terms a user means.

        Tries, in order, the query as an identifier, an abbreviation, an alias, an abbreviation ignoring case, and a
        name ignoring case, and stops at the first rule that matches anything. A rule matching several terms (2026
        uses ``LH`` for both the lateral habenula and the left hemisphere) returns them all.
        """
        if not isinstance(query, str):
            raise TypeError(
                f"structures are named by string; for annotation value {query!r} use by_value, "
                f"or name the identifier, e.g. 'MBA:{query}'"
            )
        q = query.strip()
        if q in self._by_id:
            return Match(query, (self._by_id[q],), "identifier")
        if q in self._names["abbreviation"]:
            return Match(query, tuple(self._names["abbreviation"][q]), "abbreviation")
        if q in self.aliases:
            return Match(query, tuple(self._names["abbreviation"][self.aliases[q]]), "alias")
        for kind in ("abbreviation_ci", "name_ci"):
            if q.casefold() in self._names[kind]:
                return Match(query, tuple(self._names[kind][q.casefold()]), kind)
        return Match(query, (), None)

    def term(self, query: StructureRef) -> Term:
        """Resolve ``query`` to exactly one term.

        Raises
        ------
        StructureNotFoundError
            Nothing matches; ``suggestions`` holds close names.
        AmbiguousStructureError
            Several terms match equally well; ``candidates`` holds them.
        """
        if isinstance(query, Term):
            if self._by_id.get(query.identifier) != query:
                raise StructureNotFoundError(f"{query.identifier} is not a term of {self.name} {self.version}", [])
            return query
        match = self.resolve(query)
        if match.term is not None:
            return match.term
        where = f"{self.name} {self.version}"
        if match.ambiguous:
            listed = ", ".join(f"{t.identifier} ({t.name})" for t in match.terms)
            raise AmbiguousStructureError(f"{query!r} could be {listed} in {where}; name one", match.terms)
        suggestions = self.search(query, limit=5)
        hint = (
            f"; did you mean {', '.join(f'{t.abbreviation} ({t.name})' for t in suggestions)}?" if suggestions else ""
        )
        raise StructureNotFoundError(f"no structure {query!r} in {where}{hint}", suggestions)

    def terms_for(self, queries: Iterable[StructureRef]) -> list[Term]:
        """Resolve several queries, reporting every failure at once rather than the first."""
        terms, errors = [], []
        for q in queries:
            try:
                terms.append(self.term(q))
            except LookupError as err:
                errors.append(str(err))
        if errors:
            raise LookupError("; ".join(errors))
        return terms

    def search(self, text: str, limit: int | None = 50) -> list[Term]:
        """Return terms whose abbreviation or name contains ``text``, ignoring case.

        Exact abbreviations rank first, then abbreviation prefixes, then the rest, each in ontology order.
        """
        needle = text.strip().casefold()
        if not needle:
            return []

        def rank(t: Term) -> tuple[int, int]:
            abbreviation = t.abbreviation.casefold()
            tier = 0 if abbreviation == needle else 1 if abbreviation.startswith(needle) else 2
            return tier, self._rank_of(t)

        hits = [t for t in self.terms if needle in t.abbreviation.casefold() or needle in t.name.casefold()]
        return sorted(hits, key=rank)[:limit]

    # ------------------------------------------------------------------ tree

    def parent(self, query: StructureRef) -> Term | None:
        """Return the structure directly containing ``query``; ``None`` for a root."""
        parent = self.term(query).parent_identifier
        return self._by_id[parent] if parent else None

    def children(self, query: StructureRef) -> list[Term]:
        """Return the structures directly inside ``query``, in sibling order."""
        return [self._by_id[i] for i in self._children[self.term(query).identifier]]

    def is_leaf(self, query: StructureRef) -> bool:
        """Report whether ``query`` has no substructures."""
        return not self._children[self.term(query).identifier]

    def depth(self, query: StructureRef) -> int:
        """Count the structures above ``query``; a root has depth 0."""
        return self._depth[self.term(query).identifier]

    def ancestors(self, query: StructureRef, *, include_self: bool = False) -> list[Term]:
        """Return the structures containing ``query``, outermost first."""
        term = self.term(query)
        chain = [term] if include_self else []
        while term.parent_identifier is not None:
            term = self._by_id[term.parent_identifier]
            chain.append(term)
        return chain[::-1]

    def descendants(self, query: StructureRef, *, include_self: bool = True) -> list[Term]:
        """Return ``query``'s subtree in ontology order."""
        top = self.term(query).identifier
        out: list[Term] = []
        stack = [top]
        while stack:
            node = stack.pop()
            if node != top or include_self:
                out.append(self._by_id[node])
            stack.extend(reversed(self._children[node]))
        return out

    def ancestor_at(self, query: StructureRef, depth: int) -> Term:
        """Return the structure at ``depth`` containing ``query``, or ``query`` itself if it is no deeper."""
        chain = self.ancestors(query, include_self=True)
        return chain[min(depth, len(chain) - 1)]

    def partition(self, query: StructureRef, depth: int) -> list[Term]:
        """Tile ``query``'s subtree with structures at ``depth``.

        Returns the subtree's structures at ``depth`` plus its leaves above it, in ontology order, so every leaf of
        the subtree lies in exactly one. brainglobe's ``get_structures_at_hierarchy_level`` drops the shallow leaves.
        """
        return [
            t
            for t in self.descendants(query)
            if self._depth[t.identifier] == depth or (self._depth[t.identifier] < depth and self.is_leaf(t))
        ]

    def in_order(self, queries: Iterable[StructureRef]) -> list[Term]:
        """Return terms in ontology order, so that anatomical neighbors sit together."""
        return sorted(self.terms_for(queries), key=self._rank_of)

    # ------------------------------------------------------------------ annotation values

    def annotation_values(self, query: StructureRef) -> set[int]:
        """Return the annotation values of ``query`` and everything beneath it.

        An annotation volume labels each voxel with its finest structure, so a parent covers its descendants' values.
        """
        return {t.annotation_value for t in self.descendants(query) if t.annotation_value is not None}

    def values_present(self, query: StructureRef, present: Iterable[int]) -> list[int]:
        """Return the annotation values under ``query`` that occur in ``present``, sorted.

        ``present`` is typically the unique values of an annotation volume; for one signed by hemisphere use
        :func:`.lateral.values_present`. Raises ``LookupError`` if none occur, which usually means the wrong release
        or a structure the annotation never labels.
        """
        found = sorted({int(v) for v in present} & self.annotation_values(query))
        if not found:
            term = self.term(query)
            raise LookupError(
                f"no voxel of the annotation is in {term.abbreviation} ({term.name}) or beneath it "
                f"under {self.name} {self.version}"
            )
        return found

    # ------------------------------------------------------------------ tables

    def to_records(self) -> list[dict[str, Any]]:
        """Return one dict per term in ontology order, with its depth and the columns brainglobe uses.

        ``pandas.DataFrame(terminology.to_records())`` gives the table brainglobe calls ``lookup_df``.

        ``acronym`` repeats ``abbreviation``, ``id`` is the identifier's number, and ``structure_id_path`` lists the
        ids from the root down, as in brainglobe's structure records.
        """

        def number(identifier: str) -> int | None:
            suffix = identifier.rpartition(":")[2]
            return int(suffix) if suffix.isdigit() else None

        return [
            {
                "identifier": t.identifier,
                "parent_identifier": t.parent_identifier,
                "annotation_value": t.annotation_value,
                "name": t.name,
                "abbreviation": t.abbreviation,
                "color": t.color,
                "depth": self._depth[t.identifier],
                "acronym": t.abbreviation,
                "id": number(t.identifier),
                "structure_id_path": [number(a.identifier) for a in self.ancestors(t, include_self=True)],
            }
            for t in self
        ]
