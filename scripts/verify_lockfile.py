"""Verify the structural guarantees required by requirements.lock.

This check is intentionally offline.  It validates that the checked-in lock
file is suitable for pip's ``--require-hashes`` mode; pip remains responsible
for checking a downloaded file against the listed hashes during installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

_PACKAGE_LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?)==(?P<version>[^;\\\s]+)"
    r"(?:\s*;\s*(?P<marker>[^\\]+?))?\s*\\?$"
)
_HASH_LINE = re.compile(r"^--hash=sha256:(?P<digest>[0-9a-f]{64})\s*\\?$", re.IGNORECASE)
_NAME_NORMALIZER = re.compile(r"[-_.]+")


@dataclass(frozen=True)
class LockEntry:
    name: str
    version: str
    marker: str | None
    hashes: tuple[str, ...]


def _normalize_name(name: str) -> str:
    return _NAME_NORMALIZER.sub("-", name.split("[", 1)[0].casefold())


def parse_lockfile(text: str) -> list[LockEntry]:
    entries: list[LockEntry] = []
    current: list[str] | None = None

    def finish() -> None:
        nonlocal current
        if not current:
            return
        match = _PACKAGE_LINE.fullmatch(current[0])
        if match is None:
            raise ValueError(f"invalid pinned requirement line: {current[0]!r}")
        hashes: list[str] = []
        for raw_line in current[1:]:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            hash_match = _HASH_LINE.fullmatch(line)
            if hash_match is None:
                raise ValueError(f"unexpected lockfile continuation: {raw_line!r}")
            hashes.append(hash_match.group("digest").lower())
        if not hashes:
            raise ValueError(f"{match.group('name')} has no SHA-256 hash")
        if len(hashes) != len(set(hashes)):
            raise ValueError(f"{match.group('name')} contains duplicate SHA-256 hashes")
        entries.append(
            LockEntry(
                name=_normalize_name(match.group("name")),
                version=match.group("version"),
                marker=match.group("marker").strip() if match.group("marker") else None,
                hashes=tuple(hashes),
            )
        )
        current = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            if current is not None:
                current.append(stripped)
            continue
        if _PACKAGE_LINE.fullmatch(stripped):
            finish()
            current = [stripped]
            continue
        if current is not None and (_HASH_LINE.fullmatch(stripped) or stripped.startswith("#")):
            current.append(stripped)
            continue
        raise ValueError(f"unexpected lockfile line: {raw_line!r}")
    finish()
    if not entries:
        raise ValueError("lockfile contains no pinned requirements")

    identities = [(entry.name, entry.marker or "") for entry in entries]
    if len(identities) != len(set(identities)):
        raise ValueError("lockfile contains duplicate package entries for the same marker")
    return entries


def verify_lockfile(path: Path) -> dict[str, int | str]:
    content = path.read_text(encoding="utf-8")
    entries = parse_lockfile(content)
    digest = hashlib.sha256(content.replace("\r\n", "\n").encode("utf-8")).hexdigest().upper()
    return {
        "path": path.as_posix(),
        "package_count": len(entries),
        "hash_count": sum(len(entry.hashes) for entry in entries),
        "sha256": digest,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lockfile", type=Path)
    args = parser.parse_args()
    summary = verify_lockfile(args.lockfile.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
