"""Shared domain-profile registry models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegistryDocument:
    """One immutable, versioned profile data document."""

    name: str
    version: str
    content_hash: str
    payload: dict[str, Any]
