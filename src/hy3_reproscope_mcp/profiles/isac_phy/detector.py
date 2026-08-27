"""Conservative deterministic activation signals for the ISAC profile."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...loaders import LoadedBundle
from .constants import ISAC_DEFAULT_ACTIVATION_THRESHOLD

_EXPLICIT_PATTERNS = {
    "integrated sensing and communication": r"\bintegrated sensing and communications?\b",
    "integrated sensing and communications": r"\bintegrated sensing and communications\b",
    "joint communication and sensing": r"\bjoint communications? and (?:radar )?sensing\b",
    "joint radar and communication": r"\bjoint radar(?:-|\s+and\s+)communications?\b",
    "dual-functional radar communication": r"\bdual[- ]functional radar[- ]communications?\b",
    "DFRC": r"\bdfrc\b",
    "ISAC": r"\bisac\b",
}
_JOINT_DESIGN_PATTERNS = {
    "joint beamforming": r"\bjoint (?:transmit )?beamform(?:ing|er)\b",
    "joint waveform": r"\bjoint waveform (?:design|optimization)\b",
    "shared waveform": r"\bshared (?:transmit )?waveform\b",
    "communication-sensing tradeoff": r"\b(?:communication|rate).{0,60}(?:sensing|crb).{0,40}trade[- ]?off\b",
    "Pareto tradeoff": r"\bpareto\b",
}
_COMMUNICATION_PATTERNS = {
    "communication rate": r"\b(?:achievable|sum|communication) rate\b",
    "spectral efficiency": r"\bspectral efficiency\b",
    "communication SINR": r"\b(?:communication|user).{0,30}\bsinr\b",
    "BER/BLER": r"\b(?:ber|bler|bit error rate|block error rate)\b",
}
_SENSING_PATTERNS = {
    "detection probability": r"\b(?:detection probability|probability of detection|p_d|pd)\b",
    "false alarm probability": r"\b(?:false alarm probability|probability of false alarm|p_fa|pfa)\b",
    "Cramer-Rao bound": r"\b(?:cramer.?rao bound|crb)\b",
    "range-Doppler": r"\brange[- ]doppler\b",
    "target parameter estimation": r"\b(?:range|velocity|doppler|angle) (?:estimation|rmse)\b",
    "sensing beampattern": r"\b(?:sensing|radar) beampattern\b",
}


@dataclass(frozen=True)
class IsacDetection:
    confidence: float
    matched_signals: tuple[str, ...]
    ambiguous_signals: tuple[str, ...]
    source_ids: tuple[str, ...]

    @property
    def detected(self) -> bool:
        return self.detected_at(ISAC_DEFAULT_ACTIVATION_THRESHOLD)

    def detected_at(self, threshold: float = ISAC_DEFAULT_ACTIVATION_THRESHOLD) -> bool:
        """Return activation at an explicit threshold in ``[0, 1]``.

        Keeping the threshold as a parameter makes calibration reproducible and
        avoids silently changing the production default when a labelled dataset
        is being tuned.
        """

        if not 0 <= threshold <= 1:
            raise ValueError("ISAC activation threshold must be between 0 and 1")
        return self.confidence >= threshold


def detect_isac_profile(bundle: LoadedBundle) -> IsacDetection:
    """Detect ISAC only from combined communication-and-sensing evidence."""

    source_texts = {
        source.source_id: "\n".join(segment.text for segment in source.segments).casefold() for source in bundle.sources
    }
    combined = "\n".join(source_texts.values())

    explicit = _matches(combined, _EXPLICIT_PATTERNS)
    joint = _matches(combined, _JOINT_DESIGN_PATTERNS)
    communication = _matches(combined, _COMMUNICATION_PATTERNS)
    sensing = _matches(combined, _SENSING_PATTERNS)

    if explicit:
        confidence = 0.90
        if communication and sensing:
            confidence = 0.98
    else:
        confidence = 0.0
        if joint:
            confidence += 0.35
        if communication:
            confidence += 0.20
        if sensing:
            confidence += 0.20
        if joint and communication and sensing:
            confidence += 0.25
        confidence = min(confidence, 0.95)

    matched = tuple(dict.fromkeys([*explicit, *joint, *communication, *sensing]))
    ambiguous = () if confidence >= 0.80 else matched
    source_ids = tuple(
        source_id
        for source_id, text in source_texts.items()
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _all_patterns())
    )
    return IsacDetection(
        confidence=round(confidence, 4),
        matched_signals=matched if confidence >= 0.80 else (),
        ambiguous_signals=ambiguous,
        source_ids=source_ids,
    )


def _matches(text: str, patterns: dict[str, str]) -> list[str]:
    return [label for label, pattern in patterns.items() if re.search(pattern, text, flags=re.IGNORECASE)]


def _all_patterns() -> tuple[str, ...]:
    return tuple(
        [
            *_EXPLICIT_PATTERNS.values(),
            *_JOINT_DESIGN_PATTERNS.values(),
            *_COMMUNICATION_PATTERNS.values(),
            *_SENSING_PATTERNS.values(),
        ]
    )
