"""Re-download the vendored terminology releases and pin them in ``sources.json``.

Allen rewrites published files in place, so a release's contents can change without a new version. Run this to pick
up such changes deliberately; it reports which files differ from the pinned ones, and a change is a reviewed commit and
a version bump rather than drift on a user's machine.

    uv run python scripts/update_terminologies.py                          # refresh every vendored release
    uv run python scripts/update_terminologies.py allen-adult-mouse-terminology 2027   # add a release
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REMOTE = "https://allen-atlas-assets.s3.amazonaws.com/terminologies"
DATA = Path(__file__).resolve().parents[1] / "src" / "aind_atlas_terminology" / "data"
SOURCES = DATA / "sources.json"
REQUIRED = ("manifest.json", "terminology.csv")
OPTIONAL = ("data_description.json", "legacy_files/adult_mouse_ccf_structures.csv")


def fetch(url: str) -> tuple[bytes, dict[str, str]] | None:
    """Download ``url``; ``None`` if the bucket has no such key."""
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read(), {
                "etag": resp.headers["ETag"].strip('"'),
                "last_modified": resp.headers["Last-Modified"],
            }
    except urllib.error.HTTPError as err:
        if err.code in (403, 404):
            return None
        raise


def update(name: str, version: str, sources: dict) -> list[str]:
    """Download one release into the package and pin it; return a line per changed file."""
    pinned = sources.get(name, {}).get(version, {})
    entry: dict[str, dict[str, str]] = {}
    changes = []
    for rel in REQUIRED + OPTIONAL:
        got = fetch(f"{REMOTE}/{name}/{version}/{rel}")
        if got is None:
            if rel in REQUIRED:
                raise SystemExit(f"{name} {version}: {rel} is missing from the bucket")
            continue
        content, headers = got
        digest = hashlib.sha256(content).hexdigest()
        entry[rel] = {"sha256": digest, **headers}
        before = pinned.get(rel, {}).get("sha256")
        if before != digest:
            changes.append(f"{name} {version} {rel}: {'added' if before is None else 'changed'}")
        target = DATA / name / version / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    changes += [f"{name} {version} {rel}: removed" for rel in pinned.keys() - entry.keys()]
    sources.setdefault(name, {})[version] = entry
    return changes


def main(argv: list[str]) -> None:
    """Refresh every pinned release, or add the one named on the command line."""
    sources = json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else {}
    targets = [tuple(argv)] if argv else [(n, v) for n, versions in sources.items() for v in versions]
    if not targets:
        raise SystemExit("nothing pinned yet: name a release, e.g. allen-adult-mouse-terminology 2017")
    changes = [line for name, version in targets for line in update(name, version, sources)]
    # versions keep the order they were added in; sorting strings would put 2026 before 2026-03
    SOURCES.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    print("\n".join(changes) if changes else "no changes")


if __name__ == "__main__":
    main(sys.argv[1:])
