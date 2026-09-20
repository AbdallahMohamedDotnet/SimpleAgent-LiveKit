from datetime import UTC, datetime

import pytest

from interview_app.domain.models import (
    DeliveryStatus,
    Speaker,
    StageId,
    TurnId,
    TurnRecord,
)
from interview_app.domain.scoring import (
    AssessmentStatus,
    AssessmentValidationError,
    CompetencyAssessment,
    EvidenceCitation,
    validate_stage_assessment,
)
from interview_app.resources.rubrics import HR_RUBRIC_V1

NOW = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)


def _turn(turn_id: str, speaker: Speaker, text: str) -> TurnRecord:
    return TurnRecord(
        id=TurnId(turn_id),
        stage_id=StageId("stage-score"),
        speaker=speaker,
        text=text,
        is_final=True,
        delivery_status=DeliveryStatus.DELIVERED,
        occurred_at=NOW,
    )


def _valid_assessments() -> tuple[CompetencyAssessment, ...]:
    return (
        CompetencyAssessment(
            competency="collaboration",
            score=4,
            rationale="The answer describes involving peers and resolving the work issue.",
            evidence=(EvidenceCitation(TurnId("candidate-1"), "asked two peers to review"),),
        ),
        CompetencyAssessment(
            competency="ownership",
            score=2,
            rationale="The answer gives limited follow-through evidence.",
            evidence=(EvidenceCitation(TurnId("candidate-1"), "I wrote the decision record"),),
        ),
        CompetencyAssessment(
            competency="feedback_reception",
            score=None,
            rationale="Feedback was not discussed.",
            evidence=(),
            limitation="No final candidate turn addresses received feedback.",
        ),
        CompetencyAssessment(
            competency="conflict_handling",
            score=None,
            rationale="Conflict handling was not sufficiently explored.",
            evidence=(),
            limitation="The short interview ended before a conflict example.",
        ),
    )


def test_scoring_excludes_nulls_and_preserves_coverage() -> None:
    turns = (
        _turn(
            "candidate-1",
            Speaker.CANDIDATE,
            "I asked two peers to review the options, then I wrote the decision record.",
        ),
    )
    result = validate_stage_assessment(
        rubric=HR_RUBRIC_V1,
        turns=turns,
        assessments=_valid_assessments(),
    )

    assert result.average == 3.0
    assert result.assessed_count == 2
    assert result.total_count == 4
    assert result.competencies[0].status is AssessmentStatus.ASSESSED
    assert result.competencies[2].status is AssessmentStatus.INSUFFICIENT_EVIDENCE
    assert [item.competency for item in result.competencies] == [
        item.key for item in HR_RUBRIC_V1.competencies
    ]


@pytest.mark.parametrize(
    "changed",
    [
        CompetencyAssessment(
            competency="collaboration",
            score=6,
            rationale="Out of range.",
            evidence=(EvidenceCitation(TurnId("candidate-1"), "asked two peers"),),
        ),
        CompetencyAssessment(
            competency="collaboration",
            score=4,
            rationale="Fabricated quote.",
            evidence=(EvidenceCitation(TurnId("candidate-1"), "a quote not in the answer"),),
        ),
        CompetencyAssessment(
            competency="collaboration",
            score=4,
            rationale="Question text is not candidate evidence.",
            evidence=(EvidenceCitation(TurnId("interviewer-1"), "What did you do?"),),
        ),
    ],
)
def test_scoring_rejects_invalid_or_fabricated_evidence(
    changed: CompetencyAssessment,
) -> None:
    turns = (
        _turn("candidate-1", Speaker.CANDIDATE, "I asked two peers to review the options."),
        _turn("interviewer-1", Speaker.INTERVIEWER, "What did you do?"),
    )
    assessments = (changed, *_valid_assessments()[1:])

    with pytest.raises(AssessmentValidationError):
        validate_stage_assessment(
            rubric=HR_RUBRIC_V1,
            turns=turns,
            assessments=assessments,
        )


def test_all_unassessed_produces_null_average() -> None:
    assessments = tuple(
        CompetencyAssessment(
            competency=item.key,
            score=None,
            rationale="There is not enough evidence.",
            evidence=(),
            limitation="No relevant final candidate answer was captured.",
        )
        for item in HR_RUBRIC_V1.competencies
    )
    result = validate_stage_assessment(
        rubric=HR_RUBRIC_V1,
        turns=(),
        assessments=assessments,
    )
    assert result.average is None
    assert result.assessed_count == 0
