from __future__ import annotations

import pytest

from hy3_reproeval.models import DimensionId, ErrorCode
from hy3_reproeval.rubric import load_public_rubric


def test_public_rubric_has_seven_dimensions_and_normalized_weights() -> None:
    rubric = load_public_rubric()

    assert {dimension.id for dimension in rubric.dimensions} == set(DimensionId)
    assert sum(dimension.weight for dimension in rubric.dimensions) == pytest.approx(1.0)
    assert all(set(dimension.anchors) == {0, 2, 4} for dimension in rubric.dimensions)


def test_public_rubric_registers_critical_deterministic_caps() -> None:
    rubric = load_public_rubric()

    assert rubric.hard_caps[ErrorCode.FABRICATED_CITATION] == 40
    assert rubric.hard_caps[ErrorCode.ARTIFACT_LINEAGE_ERROR] == 40
    assert rubric.hard_caps[ErrorCode.NUMERIC_ERROR] == 50
