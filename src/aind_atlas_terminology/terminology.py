"""Atlas-assets terminologies: load one, resolve structures in it, and select subtrees.

A terminology is the hierarchy of structures an atlas's annotation volumes label, stored as described by the
atlas-assets specification (https://atlas-assets.readthedocs.io): ``terminology.csv`` with ``identifier``,
``parent_identifier``, ``annotation_value``, ``name``, ``abbreviation`` and ``color_hex_triplet``, beside a
``manifest.json`` naming the release.
"""

from __future__ import annotations

import csv
import json
import shutil
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Literal

DEFAULT_REMOTE = "https://allen-atlas-assets.s3.amazonaws.com"
"""Public bucket holding Allen's atlas assets."""

BUNDLED = (("allen-adult-mouse-terminology", "2017"),)
"""Terminologies shipped with the package, as ``(name, version)``."""

# Spellings in the IBL / structure_tree_safe_2017 copy of the Allen ontology that differ from Allen's own.
ALLEN_MOUSE_ALIASES = {
    "CUL4 5": "CUL4, 5",
    "CUL4 5gr": "CUL4, 5gr",
    "CUL4 5mo": "CUL4, 5mo",
    "CUL4 5pu": "CUL4, 5pu",
    "Mmme": "MMme",
    "Mml": "MMl",
    "Mmm": "MMm",
    "Mmp": "MMp",
    "Mmd": "MMd",
}

MatchKind = Literal["identifier", "annotation_value", "abbreviation", "alias", "abbreviation_ci", "name_ci"]
Hemisphere = Literal["left", "right"]


@dataclass(frozen=True, slots=True)
class Term:
    """One structure of a terminology."""

    identifier: str
    """Stable id, e.g. ``MBA:223``."""
    parent_identifier: str | None
    annotation_value: int | None
    """Value labelling the structure in annotation volumes; ``None`` if no volume labels it."""
    name: str
    abbreviation: str
    color: str
    """Display color, ``#RRGGBB``."""


@dataclass(frozen=True, slots=True)
class Match:
    """How a query resolved; ``term`` and ``matched_on`` are ``None`` when it did not."""

    query: str | int
    term: Term | None
    matched_on: MatchKind | None


@dataclass
class Terminology:
    """A loaded terminology, indexed for lookup and tree queries.

    Parameters
    ----------
    terms : iterable of Term
        Every structure. Terms without a parent are roots; Allen's releases since 2020 add ``unassigned`` beside
        the brain.
    name, version : str
        The release, as its manifest names it.
    aliases : dict of str to str
        Alternative abbreviations, mapped to the canonical one.
    order : dict of str to int, optional
        Sibling order by identifier (Allen's ``graph_order``); without it siblings keep their table order.
    """

    terms: Iterable[Term]
    name: str = ""
    version: str = ""
    aliases: dict[str, str] = field(default_factory=dict)
    order: dict[str, int] | None = None
    _by_id: dict[str, Term] = field(init=False, repr=False)
    _by_value: dict[int, Term] = field(init=False, repr=False)
    _by_abbreviation: dict[str, Term] = field(init=False, repr=False)
    _by_abbreviation_ci: dict[str, Term] = field(init=False, repr=False)
    _by_name_ci: dict[str, Term] = field(init=False, repr=False)
    _children: dict[str, list[str]] = field(init=False, repr=False)
    _rank: dict[str, int] = field(init=False, repr=False)
    _roots: list[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Index the terms and check that they form a forest."""
        self.terms = list(self.terms)
        self._index(self.terms)
        self._build_tree(self.terms)

    def _index(self, terms: list[Term]) -> None:
        """Build the lookup tables; the first of two terms sharing an abbreviation or name wins."""
        self._by_id = {}
        self._by_value = {}
        self._by_abbreviation = {}
        self._by_abbreviation_ci = {}
        self._by_name_ci = {}
        for t in terms:
            if t.identifier in self._by_id:
                raise ValueError(f"identifier {t.identifier} appears twice")
            self._by_id[t.identifier] = t
            if t.annotation_value is not None:
                if t.annotation_value in self._by_value:
                    raise ValueError(f"annotation_value {t.annotation_value} appears twice")
                self._by_value[t.annotation_value] = t
            self._by_abbreviation.setdefault(t.abbreviation, t)
            self._by_abbreviation_ci.setdefault(t.abbreviation.lower(), t)
            self._by_name_ci.setdefault(t.name.lower(), t)

    def _build_tree(self, terms: list[Term]) -> None:
        """Link children to parents, order siblings, and rank terms in preorder."""
        self._children = {t.identifier: [] for t in terms}
        roots = []
        for t in terms:
            if t.parent_identifier is None:
                roots.append(t.identifier)
            elif t.parent_identifier not in self._by_id:
                raise ValueError(f"{t.identifier} has unknown parent {t.parent_identifier}")
            else:
                self._children[t.parent_identifier].append(t.identifier)
        if not roots:
            raise ValueError("no root: every term has a parent")
        if self.order is not None:
            order = self.order
            for kids in [roots, *self._children.values()]:
                kids.sort(key=lambda i: order.get(i, len(order)))
        self._roots = roots
        # sorting by preorder rank keeps every subtree contiguous
        self._rank = {}
        stack = roots[::-1]
        while stack:
            node = stack.pop()
            self._rank[node] = len(self._rank)
            stack.extend(reversed(self._children[node]))
        # a term on a parent cycle is never reached from a root
        if len(self._rank) != len(terms):
            raise ValueError("some terms are not reachable from a root")

    # ------------------------------------------------------------------ loading

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        name: str = "",
        version: str = "",
        aliases: dict[str, str] | None = None,
        order: dict[str, int] | None = None,
    ) -> Terminology:
        """Read a ``terminology.csv``."""
        with open(path, newline="", encoding="utf-8") as fh:
            terms = [_term(row) for row in csv.DictReader(fh)]
        return cls(terms, name=name, version=version, aliases=aliases or {}, order=order)

    @classmethod
    def from_directory(cls, path: str | Path) -> Terminology:
        """Read a terminology release directory: ``manifest.json`` and ``terminology.csv``.

        An Allen adult mouse release also gets the IBL spellings as aliases and, where its
        ``legacy_files/adult_mouse_ccf_structures.csv`` is present, Allen's sibling order.
        """
        path = Path(path)
        manifest = json.loads((path / "manifest.json").read_text())
        name, version = manifest["name"], str(manifest["version"])
        aliases: dict[str, str] = {}
        order = None
        if name == "allen-adult-mouse-terminology":
            aliases = dict(ALLEN_MOUSE_ALIASES)
            legacy = path / "legacy_files" / "adult_mouse_ccf_structures.csv"
            if legacy.exists():
                with open(legacy, newline="", encoding="utf-8") as fh:
                    order = {f"MBA:{r['id']}": int(r["graph_order"]) for r in csv.DictReader(fh)}
        return cls.from_csv(path / "terminology.csv", name=name, version=version, aliases=aliases, order=order)

    @classmethod
    def bundled(cls, name: str = "allen-adult-mouse-terminology", version: str = "2017") -> Terminology:
        """Load a terminology shipped with the package; see :data:`BUNDLED`."""
        if (name, version) not in BUNDLED:
            raise LookupError(f"{name} {version} is not bundled; bundled: {BUNDLED}. Use Terminology.fetch.")
        ref = resources.files("aind_atlas_terminology") / "data" / name / version
        with resources.as_file(ref) as path:
            return cls.from_directory(path)

    @classmethod
    def fetch(
        cls,
        name: str,
        version: str,
        *,
        cache_dir: str | Path | None = None,
        remote: str = DEFAULT_REMOTE,
    ) -> Terminology:
        """Download a terminology release from ``remote`` once, then load it from ``cache_dir``.

        The default cache is ``~/.cache/aind-atlas-terminology``.
        """
        cache = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "aind-atlas-terminology"
        local = cache / name / version
        files = ["manifest.json", "terminology.csv"]
        if name == "allen-adult-mouse-terminology":
            files.append("legacy_files/adult_mouse_ccf_structures.csv")
        for rel in files:
            target = local / rel
            absent = target.with_suffix(".absent")
            if target.exists() or absent.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f"{remote.rstrip('/')}/terminologies/{name}/{version}/{rel}"
            partial = target.with_suffix(target.suffix + ".part")
            try:
                with urllib.request.urlopen(url, timeout=60) as resp, open(partial, "wb") as out:
                    shutil.copyfileobj(resp, out)
            except urllib.error.HTTPError as err:
                partial.unlink(missing_ok=True)
                # optional: only 2017 publishes it, and it only supplies sibling order
                if err.code == 404 and rel.startswith("legacy_files/"):
                    absent.touch()
                    continue
                raise
            except OSError:
                partial.unlink(missing_ok=True)
                raise
            partial.replace(target)
        return cls.from_directory(local)

    # ------------------------------------------------------------------ lookup

    def __len__(self) -> int:
        """Count the terms."""
        return len(self._by_id)

    def __iter__(self) -> Iterator[Term]:
        """Terms in ontology order: every structure before its descendants, siblings in sibling order."""
        return iter(self.sorted(self._by_id.values()))

    @property
    def roots(self) -> list[Term]:
        """Terms without a parent, in sibling order."""
        return [self._by_id[i] for i in self._roots]

    def get(self, key: str | int) -> Term:
        """Look up a term by identifier (``"MBA:170"``) or by its annotation value in this release."""
        term = self._by_value.get(key) if isinstance(key, int) else self._by_id.get(key)
        if term is None:
            raise KeyError(key)
        return term

    def resolve(self, query: str | int) -> Match:
        """Find the term a user means.

        An int is an annotation value. A string is tried, in order, as an identifier, an abbreviation, an alias, an
        abbreviation ignoring case, and a name ignoring case.
        """
        if isinstance(query, int):
            term = self._by_value.get(query)
            return Match(query, term, "annotation_value" if term else None)
        q = query.strip()
        if q in self._by_id:
            return Match(query, self._by_id[q], "identifier")
        if q in self._by_abbreviation:
            return Match(query, self._by_abbreviation[q], "abbreviation")
        if q in self.aliases:
            return Match(query, self._by_abbreviation[self.aliases[q]], "alias")
        if q.lower() in self._by_abbreviation_ci:
            return Match(query, self._by_abbreviation_ci[q.lower()], "abbreviation_ci")
        if q.lower() in self._by_name_ci:
            return Match(query, self._by_name_ci[q.lower()], "name_ci")
        return Match(query, None, None)

    def term(self, query: str | int | Term) -> Term:
        """Resolve ``query`` to a term, or raise ``LookupError`` listing close candidates."""
        if isinstance(query, Term):
            return query
        match = self.resolve(query)
        if match.term is None:
            candidates = [f"{t.abbreviation} ({t.name})" for t in self.search(str(query), limit=5)]
            hint = f"; did you mean {', '.join(candidates)}?" if candidates else ""
            raise LookupError(f"no structure {query!r} in {self.name} {self.version}{hint}")
        return match.term

    def search(self, text: str, limit: int = 50) -> list[Term]:
        """Terms whose abbreviation or name contains ``text``, ignoring case.

        Exact abbreviations rank first, then abbreviation prefixes, then the rest, each in ontology order.
        """
        needle = text.strip().lower()
        if not needle:
            return []
        hits = [t for t in self._by_id.values() if needle in t.abbreviation.lower() or needle in t.name.lower()]

        def rank(t: Term) -> tuple[int, int]:
            abbreviation = t.abbreviation.lower()
            tier = 0 if abbreviation == needle else 1 if abbreviation.startswith(needle) else 2
            return tier, self._rank[t.identifier]

        return sorted(hits, key=rank)[:limit]

    # ------------------------------------------------------------------ tree

    def parent(self, query: str | int | Term) -> Term | None:
        """Return the structure directly containing ``query``; ``None`` for a root."""
        parent = self.term(query).parent_identifier
        return self._by_id[parent] if parent else None

    def children(self, query: str | int | Term) -> list[Term]:
        """Structures directly inside ``query``, in sibling order."""
        return [self._by_id[i] for i in self._children[self.term(query).identifier]]

    def ancestors(self, query: str | int | Term, *, include_self: bool = False) -> list[Term]:
        """Structures containing ``query``, outermost first."""
        term = self.term(query)
        chain = [term] if include_self else []
        while (parent := self.parent(term)) is not None:
            chain.append(parent)
            term = parent
        return chain[::-1]

    def descendants(self, query: str | int | Term, *, include_self: bool = True) -> list[Term]:
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

    def annotation_values(self, query: str | int | Term) -> set[int]:
        """Annotation values of ``query`` and everything beneath it.

        An annotation volume labels each voxel with its finest structure, so a parent covers its descendants' values.
        """
        return {t.annotation_value for t in self.descendants(query) if t.annotation_value is not None}

    def values_present(self, query: str | int | Term, present: Iterable[int]) -> list[int]:
        """Return the annotation values under ``query`` that occur in ``present``, sorted.

        ``present`` is typically the unique values of an annotation volume; a lateralized volume's negative values
        count by magnitude, and are returned with their sign. Raises ``LookupError`` if none occur, which usually
        means the wrong terminology or a structure the annotation never labels.
        """
        wanted = self.annotation_values(query)
        found = sorted({int(v) for v in present if abs(int(v)) in wanted})
        if not found:
            term = self.term(query)
            raise LookupError(f"no voxel of the annotation is in {term.abbreviation} ({term.name}) or beneath it")
        return found

    def sorted(self, queries: Iterable[str | int | Term]) -> list[Term]:
        """Terms in ontology order, so that anatomical neighbors sit together."""
        terms = [self.term(q) for q in queries]
        return sorted(terms, key=lambda t: self._rank[t.identifier])

    def depth(self, query: str | int | Term) -> int:
        """Count the structures above ``query``; a root has depth 0."""
        return len(self.ancestors(query))

    # ------------------------------------------------------------------ lateralized annotations

    def lateral(self, value: int, *, left_negative: bool = True) -> tuple[Term, Hemisphere | None]:
        """Return the term and hemisphere of a value from a lateralized annotation.

        With ``left_negative``, the convention of iblatlas and Allen's lateralized CCF annotations, a negative value
        marks the left hemisphere and a positive one the right. Value 0 is background and raises ``KeyError``.
        """
        if value == 0:
            raise KeyError(0)
        term = self.get(abs(value))
        if not left_negative:
            return term, None
        return term, "left" if value < 0 else "right"


def _term(row: dict[str, str]) -> Term:
    """Build a term from one CSV row."""
    value = row.get("annotation_value", "").strip()
    color = row.get("color_hex_triplet", "").strip().lstrip("#")
    return Term(
        identifier=row["identifier"].strip(),
        parent_identifier=row.get("parent_identifier", "").strip() or None,
        annotation_value=int(float(value)) if value else None,
        name=row["name"].strip(),
        abbreviation=row["abbreviation"].strip(),
        color="#" + color.zfill(6).upper() if color else "#808080",
    )
