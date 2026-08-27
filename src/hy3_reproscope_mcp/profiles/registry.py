"""Versioned loading of bundled domain-profile data."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import cache
from importlib.resources import files
from typing import Any

from .base import RegistryDocument

PROFILE_REGISTRY_VERSION = "1.0.0"
_ISAC_DOCUMENTS = ("taxonomy", "metrics", "assumptions", "risk_rules")


class ProfileRegistry:
    """Load package-owned profile data without accepting executable formats."""

    def isac_document(self, name: str) -> RegistryDocument:
        document = _load_isac_document(name)
        return RegistryDocument(
            name=document.name,
            version=document.version,
            content_hash=document.content_hash,
            payload=deepcopy(document.payload),
        )

    def isac_prompt_payload(self) -> dict[str, Any]:
        """Return bounded profile context for one Hy3 structured call."""

        return {name: self.isac_document(name).payload for name in _ISAC_DOCUMENTS}

    def isac_versions(self) -> dict[str, str]:
        return {
            "profile_registry": PROFILE_REGISTRY_VERSION,
            **{f"isac_{name}": self.isac_document(name).version for name in _ISAC_DOCUMENTS},
        }

    def isac_hashes(self) -> dict[str, str]:
        return {f"isac_{name}": self.isac_document(name).content_hash for name in _ISAC_DOCUMENTS}


@cache
def _load_isac_document(name: str) -> RegistryDocument:
    if name not in _ISAC_DOCUMENTS:
        raise KeyError(f"Unknown ISAC registry document: {name}")
    resource = files("hy3_reproscope_mcp.profiles.isac_phy.data").joinpath(f"{name}.json")
    raw = resource.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"ISAC registry document must contain a JSON object: {name}")
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"ISAC registry document has no version: {name}")
    if version != PROFILE_REGISTRY_VERSION:
        raise ValueError(
            f"ISAC registry document version mismatch for {name}: expected {PROFILE_REGISTRY_VERSION}, got {version}."
        )
    _validate_isac_document(name, payload)
    return RegistryDocument(
        name=name,
        version=version,
        content_hash=hashlib.sha256(raw).hexdigest(),
        payload=payload,
    )


def _validate_isac_document(name: str, payload: dict[str, Any]) -> None:
    collection_name = {
        "metrics": "metrics",
        "assumptions": "assumptions",
        "risk_rules": "rules",
    }.get(name)
    if collection_name is not None:
        items = payload.get(collection_name)
        if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
            raise ValueError(f"ISAC registry document has no valid {collection_name} collection: {name}")
        identity_key = {
            "metrics": "canonical_name",
            "assumptions": "name",
            "risk_rules": "rule_id",
        }[name]
        identities = [item.get(identity_key) for item in items]
        if not all(isinstance(identity, str) and identity for identity in identities):
            raise ValueError(f"ISAC registry document has an invalid {identity_key}: {name}")
        if len(set(identities)) != len(identities):
            raise ValueError(f"ISAC registry document has duplicate {identity_key} values: {name}")
        return

    required_taxonomies = (
        "system_types",
        "sensing_topologies",
        "waveforms",
        "research_methods",
        "evidence_levels",
    )
    for taxonomy_name in required_taxonomies:
        values = payload.get(taxonomy_name)
        if not isinstance(values, list) or not values or not all(isinstance(value, str) and value for value in values):
            raise ValueError(f"ISAC taxonomy has no valid {taxonomy_name} collection.")
        if len(set(values)) != len(values):
            raise ValueError(f"ISAC taxonomy has duplicate {taxonomy_name} values.")


registry = ProfileRegistry()
