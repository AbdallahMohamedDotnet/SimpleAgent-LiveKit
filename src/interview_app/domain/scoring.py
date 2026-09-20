"""Validated, deterministic stage scoring over immutable transcript evidence."""

from dataclasses import dataclass

from interview_app.domain.models import Speaker, TurnId, TurnRecord
from interview_app.domain.rubrics import StageRubric


class AssessmentValidationError(ValueError):
    """Raised when assessor output is incomplete or unsupported by evidence."""


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


@dataclass(frozen=True, slots=True)
class StageAssessment:
    rubric_version: str
    competencies: tuple[CompetencyAssessment, ...]
    average: float | None
    assessed_count: int
    total_count: int


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
            if assessment.evidence:
                raise AssessmentValidationError(
                    "An unassessed competency cannot carry numeric-score evidence."
                )
            if not assessment.limitation or not assessment.limitation.strip():
                raise AssessmentValidationError(
                    "An unassessed competency requires an explicit evidence limitation."
                )
        else:
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
