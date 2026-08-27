"""Resolve explicit, user-instruction, and automatic profile activation."""

from __future__ import annotations

from ...loaders import LoadedBundle
from ...models import (
    DomainActivationSource,
    DomainProfileActivation,
    DomainProfileMode,
    DomainProfileName,
    ProfileRequestSource,
)
from .. import GENERIC_PROFILE_VERSION
from .constants import ISAC_PROFILE_VERSION
from .detector import detect_isac_profile


def resolve_profile_activation(
    *,
    requested_profile: DomainProfileMode,
    request_source: ProfileRequestSource,
    bundle: LoadedBundle,
) -> DomainProfileActivation:
    """Apply the activation priority while preserving why the profile ran."""

    detection = detect_isac_profile(bundle)
    references_by_id = {source.source_id: source.reference for source in bundle.sources}
    detection_references = [
        references_by_id[source_id] for source_id in detection.source_ids if source_id in references_by_id
    ]

    if requested_profile is DomainProfileMode.GENERIC:
        return DomainProfileActivation(
            requested_profile=requested_profile,
            detected_profile=(DomainProfileName.ISAC_PHY if detection.detected else DomainProfileName.GENERIC),
            effective_profile=DomainProfileName.GENERIC,
            profile_version=GENERIC_PROFILE_VERSION,
            confidence=detection.confidence,
            activation_source=DomainActivationSource.DEFAULT_GENERIC,
            ambiguous_signals=list(detection.ambiguous_signals),
            source_references=detection_references,
        )

    if requested_profile is DomainProfileMode.ISAC_PHY:
        warnings: list[str] = []
        if not detection.detected:
            warnings.append(
                "The ISAC profile was explicitly enabled, but the supplied material contains only partial "
                "high-confidence ISAC signals; some checks may be unknown or not_applicable."
            )
        return DomainProfileActivation(
            requested_profile=requested_profile,
            detected_profile=(DomainProfileName.ISAC_PHY if detection.detected else DomainProfileName.GENERIC),
            effective_profile=DomainProfileName.ISAC_PHY,
            profile_version=ISAC_PROFILE_VERSION,
            confidence=detection.confidence,
            activation_source=(
                DomainActivationSource.USER_INSTRUCTION
                if request_source is ProfileRequestSource.USER_INSTRUCTION
                else DomainActivationSource.EXPLICIT_PARAMETER
            ),
            matched_signals=list(detection.matched_signals),
            ambiguous_signals=list(detection.ambiguous_signals),
            warnings=warnings,
            source_references=detection_references,
        )

    effective_profile = DomainProfileName.ISAC_PHY if detection.detected else DomainProfileName.GENERIC
    warnings = []
    if not detection.detected and detection.ambiguous_signals:
        warnings.append(
            "ISAC-like signals were found below the activation threshold; the generic profile remains active."
        )
    return DomainProfileActivation(
        requested_profile=requested_profile,
        detected_profile=effective_profile,
        effective_profile=effective_profile,
        profile_version=(
            ISAC_PROFILE_VERSION if effective_profile is DomainProfileName.ISAC_PHY else GENERIC_PROFILE_VERSION
        ),
        confidence=detection.confidence,
        activation_source=(
            DomainActivationSource.AUTO_DETECTION if detection.detected else DomainActivationSource.DEFAULT_GENERIC
        ),
        matched_signals=list(detection.matched_signals),
        ambiguous_signals=list(detection.ambiguous_signals),
        warnings=warnings,
        source_references=detection_references,
    )
