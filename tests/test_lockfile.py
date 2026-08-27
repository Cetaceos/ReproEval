from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_lockfile import parse_lockfile, verify_lockfile


def test_lockfile_parser_counts_hashes_and_markers() -> None:
    entries = parse_lockfile(
        """pkg-one==1.2.3 \\
    --hash=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    # via fixture
pkg-two==2.0.0 ; sys_platform == \"win32\" \\
    --hash=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
"""
    )
    assert [(entry.name, entry.marker) for entry in entries] == [
        ("pkg-one", None),
        ("pkg-two", 'sys_platform == "win32"'),
    ]
    assert sum(len(entry.hashes) for entry in entries) == 2


@pytest.mark.parametrize(
    "text",
    [
        "pkg==1.0.0\n",
        "pkg==1.0.0 \\\n+    --hash=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1\n"
        "pkg==1.0.0 \\\n+    --hash=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n",
    ],
)
def test_lockfile_parser_rejects_missing_or_duplicate_entries(text: str) -> None:
    with pytest.raises(ValueError):
        parse_lockfile(text)


def test_checked_in_lockfile_has_hashes() -> None:
    summary = verify_lockfile(Path(__file__).resolve().parents[1] / "requirements.lock")
    assert summary["package_count"] >= 40
    assert summary["hash_count"] >= summary["package_count"]
