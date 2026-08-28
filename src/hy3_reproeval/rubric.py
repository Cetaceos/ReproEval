"""Load and validate the versioned public ReproEval rubric."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

import yaml
from pydantic import Field, model_validator

from .models import DimensionId, ErrorCode, StrictModel


class DimensionRubric(StrictModel):
    id: DimensionId
    label: str = Field(min_length=1)
    weight: float = Field(gt=0, le=1)
    anchors: dict[int, str]

    @model_validator(mode="after")
    def validate_anchors(self) -> DimensionRubric:
        if set(self.anchors) != {0, 2, 4}:
            raise ValueError("dimension anchors must contain exactly 0, 2, and 4")
        if any(not text.strip() for text in self.anchors.values()):
            raise ValueError("dimension anchor text cannot be empty")
        return self


class QualityThresholds(StrictModel):
    excellent: float = Field(ge=0, le=100)
    strong: float = Field(ge=0, le=100)
    mixed: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_order(self) -> QualityThresholds:
        if not self.excellent > self.strong > self.mixed:
            raise ValueError("quality thresholds must be strictly descending")
        return self


class RubricDefinition(StrictModel):
    schema_version: str
    rubric_version: str
    minimum_assessed_weight: float = Field(ge=0, le=1)
    dimensions: list[DimensionRubric]
    quality_thresholds: QualityThresholds
    hard_caps: dict[ErrorCode, float]

    @model_validator(mode="after")
    def validate_dimensions(self) -> RubricDefinition:
        expected = set(DimensionId)
        actual = {dimension.id for dimension in self.dimensions}
        if actual != expected or len(self.dimensions) != len(expected):
            missing = sorted(item.value for item in expected - actual)
            extra = sorted(item.value for item in actual - expected)
            raise ValueError(f"rubric dimensions must match public taxonomy; missing={missing}, extra={extra}")
        total = sum(dimension.weight for dimension in self.dimensions)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"rubric dimension weights must sum to 1.0, got {total}")
        if any(not 0 <= cap <= 100 for cap in self.hard_caps.values()):
            raise ValueError("hard caps must be between 0 and 100")
        return self

    def dimension(self, dimension_id: DimensionId) -> DimensionRubric:
        return next(dimension for dimension in self.dimensions if dimension.id is dimension_id)


@lru_cache(maxsize=1)
def load_public_rubric() -> RubricDefinition:
    rubric_path = files("hy3_reproeval.data").joinpath("rubric.yaml")
    payload = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
    return RubricDefinition.model_validate(payload)
