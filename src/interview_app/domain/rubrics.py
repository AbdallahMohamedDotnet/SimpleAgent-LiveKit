"""Typed rubric boundaries independent of storage and provider SDKs."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompetencyRubric:
    key: str
    description: str
    low_anchor: str
    high_anchor: str


@dataclass(frozen=True, slots=True)
class StageRubric:
    version: str
    competencies: tuple[CompetencyRubric, ...]
