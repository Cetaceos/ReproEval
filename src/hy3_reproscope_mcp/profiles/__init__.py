"""Optional domain profiles layered on the generic evidence-audit workflow."""

from .registry import ProfileRegistry, registry

GENERIC_PROFILE_VERSION = "1.0.0"

__all__ = ["GENERIC_PROFILE_VERSION", "ProfileRegistry", "registry"]
