"""Validated, deterministic stage scoring over immutable transcript evidence."""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from interview_app.domain.models import (
    ScoreTaskId,
    SnapshotId,
    Speaker,
    StageId,
    StageKind,
    TurnId,
    TurnRecord,
)
from interview_app.domain.rubrics import StageRubric


class AssessmentValidationError(ValueError):
    """Raised when assessor output is incomplete or unsupported by evidence."""


class AssessmentStatus(StrEnum):
    ASSESSED = "assessed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class EvidenceCitation:
    turn_id: TurnId
    quote: str


@dataclass(frozen=True, slots=True)
class CompetencyAssessment:
    competency: str
    score: int | None
    rationale: str
    evidence: tuple[EvidenceCitation, ...]
    limitation: str | None = None
    status: AssessmentStatus | None = None
    difficulty: str | None = None
    assistance: str | None = None


@dataclass(frozen=True, slots=True)
class StageAssessment:
    rubric_version: str
    competencies: tuple[CompetencyAssessment, ...]
    average: float | None
    assessed_count: int
    total_count: int


@dataclass(frozen=True, slots=True)
class AssessmentTaskInput:
    task_id: ScoreTaskId
    snapshot_id: SnapshotId
    stage_id: StageId
    stage_kind: StageKind
    rubric_version: str
    turns: tuple[TurnRecord, ...]


@dataclass(frozen=True, slots=True)
class ParsedAssessment:
    competencies: tuple[CompetencyAssessment, ...]
    summary: str | None


@dataclass(frozen=True, slots=True)
class StageScoreRecord:
    task_id: ScoreTaskId
    snapshot_id: SnapshotId
    stage_id: StageId
    rubric_version: str
    model: str
    assessment: StageAssessment
    summary: str | None
    created_at: datetime


def parse_assessment_json(payload: str) -> ParsedAssessment:
    """Parse the strict provider boundary without trusting extra output fields."""
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as error:
        raise AssessmentValidationError("Assessor output is not valid JSON.") from error
    if not isinstance(decoded, dict) or set(decoded) != {"competencies", "summary"}:
        raise AssessmentValidationError(
            "Assessor output must contain only competencies and summary."
        )
    raw_competencies = decoded["competencies"]
    if not isinstance(raw_competencies, list):
        raise AssessmentValidationError("competencies must be a JSON array.")
    summary_value = decoded["summary"]
    if summary_value is not None and not isinstance(summary_value, str):
        raise AssessmentValidationError("summary must be a string or null.")
    summary = summary_value.strip() if isinstance(summary_value, str) else None
    if summary == "":
        summary = None

    competencies = tuple(_parse_competency(item) for item in raw_competencies)
    return ParsedAssessment(competencies=competencies, summary=summary)


def _parse_competency(value: object) -> CompetencyAssessment:
    if not isinstance(value, dict):
        raise AssessmentValidationError("Each competency must be a JSON object.")
    required = {"competency", "status", "score", "rationale", "evidence", "limitation"}
    optional = {"difficulty", "assistance"}
    keys = set(value)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise AssessmentValidationError("Competency output has missing or unexpected fields.")
    competency = value["competency"]
    rationale = value["rationale"]
    limitation = value["limitation"]
    difficulty = value.get("difficulty")
    assistance = value.get("assistance")
    if not isinstance(competency, str) or not isinstance(rationale, str):
        raise AssessmentValidationError("Competency and rationale must be strings.")
    for field_name, item in (
        ("limitation", limitation),
        ("difficulty", difficulty),
        ("assistance", assistance),
    ):
        if item is not None and not isinstance(item, str):
            raise AssessmentValidationError(f"{field_name} must be a string or null.")
    try:
        status = AssessmentStatus(value["status"])
    except (TypeError, ValueError) as error:
        raise AssessmentValidationError("Unknown competency assessment status.") from error
    score = value["score"]
    if score is not None and (isinstance(score, bool) or not isinstance(score, int)):
        raise AssessmentValidationError("score must be an integer or null.")
    raw_evidence = value["evidence"]
    if not isinstance(raw_evidence, list):
        raise AssessmentValidationError("evidence must be a JSON array.")
    evidence: list[EvidenceCitation] = []
    for citation in raw_evidence:
        if not isinstance(citation, dict) or set(citation) != {"turn_id", "quote"}:
            raise AssessmentValidationError("Evidence must contain only turn_id and quote.")
        turn_id = citation["turn_id"]
        quote = citation["quote"]
        if not isinstance(turn_id, str) or not isinstance(quote, str):
            raise AssessmentValidationError("Evidence turn_id and quote must be strings.")
        evidence.append(EvidenceCitation(turn_id=TurnId(turn_id), quote=quote))
    return CompetencyAssessment(
        competency=competency,
        score=cast(int | None, score),
        rationale=rationale,
        evidence=tuple(evidence),
        limitation=cast(str | None, limitation),
        status=status,
        difficulty=cast(str | None, difficulty),
        assistance=cast(str | None, assistance),
    )


def validate_stage_assessment(
    *,
    rubric: StageRubric,
    turns: tuple[TurnRecord, ...],
    assessments: tuple[CompetencyAssessment, ...],
) -> StageAssessment:
    expected_keys = tuple(item.key for item in rubric.competencies)
    actual_keys = tuple(item.competency for item in assessments)
    if len(set(actual_keys)) != len(actual_keys):
        raise AssessmentValidationError("Competency keys must be unique.")
    if set(actual_keys) != set(expected_keys):
        raise AssessmentValidationError("Assessment must contain every expected competency once.")

    turns_by_id = {turn.id: turn for turn in turns}
    validated_by_key: dict[str, CompetencyAssessment] = {}
    numeric_scores: list[int] = []
    for assessment in assessments:
        rationale = assessment.rationale.strip()
        if not rationale:
            raise AssessmentValidationError("Every competency requires a concise rationale.")
        if assessment.score is None:
            if assessment.status not in {None, AssessmentStatus.INSUFFICIENT_EVIDENCE}:
                raise AssessmentValidationError(
                    "A null score must have insufficient_evidence status."
                )
            if assessment.evidence:
                raise AssessmentValidationError(
                    "An unassessed competency cannot carry numeric-score evidence."
                )
            if not assessment.limitation or not assessment.limitation.strip():
                raise AssessmentValidationError(
                    "An unassessed competency requires an explicit evidence limitation."
                )
        else:
            if assessment.status not in {None, AssessmentStatus.ASSESSED}:
                raise AssessmentValidationError("A numeric score must have assessed status.")
            if isinstance(assessment.score, bool) or not 1 <= assessment.score <= 5:
                raise AssessmentValidationError("Competency scores must be integers from 1 to 5.")
            if not assessment.evidence:
                raise AssessmentValidationError("Every numeric score requires transcript evidence.")
            for citation in assessment.evidence:
                turn = turns_by_id.get(citation.turn_id)
                if turn is None:
                    raise AssessmentValidationError(
                        "Evidence references an unknown transcript turn."
                    )
                if turn.speaker is not Speaker.CANDIDATE:
                    raise AssessmentValidationError("Scores must cite candidate-answer evidence.")
                quote = citation.quote.strip()
                if not quote or quote not in turn.text:
                    raise AssessmentValidationError(
                        "Evidence quote must be an exact non-empty span of its source turn."
                    )
            numeric_scores.append(assessment.score)
        validated_by_key[assessment.competency] = CompetencyAssessment(
            competency=assessment.competency,
            score=assessment.score,
            rationale=rationale,
            evidence=assessment.evidence,
            limitation=assessment.limitation.strip() if assessment.limitation else None,
            status=(
                AssessmentStatus.ASSESSED
                if assessment.score is not None
                else AssessmentStatus.INSUFFICIENT_EVIDENCE
            ),
            difficulty=assessment.difficulty.strip() if assessment.difficulty else None,
            assistance=assessment.assistance.strip() if assessment.assistance else None,
        )

    ordered = tuple(validated_by_key[key] for key in expected_keys)
    average = sum(numeric_scores) / len(numeric_scores) if numeric_scores else None
    return StageAssessment(
        rubric_version=rubric.version,
        competencies=ordered,
        average=average,
        assessed_count=len(numeric_scores),
        total_count=len(expected_keys),
    )
