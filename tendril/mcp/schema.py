"""Pydantic v2 input models for the five MCP tool endpoints (SPEC.md §4, M5-3)."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

_VALID_CONFIDENCES = {"high", "medium", "low"}


class FindRelevantReposInput(BaseModel):
    task: str
    env: str
    max_hops: int = 3
    min_confidence: str = "low"

    @field_validator("min_confidence")
    @classmethod
    def _validate_confidence(cls, v: str) -> str:
        if v not in _VALID_CONFIDENCES:
            raise ValueError(f"min_confidence must be one of {sorted(_VALID_CONFIDENCES)}")
        return v


class ImpactAnalysisInput(BaseModel):
    repo_id: str
    env: str
    min_confidence: str = "low"

    @field_validator("min_confidence")
    @classmethod
    def _validate_confidence(cls, v: str) -> str:
        if v not in _VALID_CONFIDENCES:
            raise ValueError(f"min_confidence must be one of {sorted(_VALID_CONFIDENCES)}")
        return v


class DependencyPathInput(BaseModel):
    from_id: str
    to_id: str
    env: str


class EnvDiffInput(BaseModel):
    repo_id: str
    env_a: str
    env_b: str


class ExplainEdgeInput(BaseModel):
    from_id: str
    to_id: str
    env: str
