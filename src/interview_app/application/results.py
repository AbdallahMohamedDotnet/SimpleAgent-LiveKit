"""Immutable DTOs for the read-only results boundary."""

from dataclasses import dataclass
from datetime import datetime

from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewState,
    RecordingSegmentId,
    RecordingStatus,
    ScoreTaskState,
    Speaker,
    StageId,
    StageKind,
    StageState,
    TurnId,
)
from interview_app.domain.scoring import AssessmentStatus


@dataclass(frozen=True, slots=True)
class StageSummary:
    kind: StageKind
    state: StageState
    assessment_state: ScoreTaskState | None
    average: float | None
    assessed_count: int | None
    total_count: int | None


@dataclass(frozen=True, slots=True)
class InterviewSummary:
    id: InterviewId
    candidate_name: str
    state: InterviewState
    created_at: datetime
    stages: tuple[StageSummary, ...]


@dataclass(frozen=True, slots=True)
class ResultTurn:
    id: TurnId
    speaker: Speaker
    text: str
    delivery_status: DeliveryStatus
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ResultEvidence:
    turn_id: TurnId
    quote: str


@dataclass(frozen=True, slots=True)
class CompetencyResult:
    name: str
    status: AssessmentStatus
    score: int | None
    rationale: str
    limitation: str | None
    difficulty: str | None
    assistance: str | None
    evidence: tuple[ResultEvidence, ...]


@dataclass(frozen=True, slots=True)
class AssessmentResult:
    state: ScoreTaskState
    average: float | None
    assessed_count: int | None
    total_count: int | None
    summary: str | None
    failure: str | None
    competencies: tuple[CompetencyResult, ...]


@dataclass(frozen=True, slots=True)
class RecordingGapResult:
    offset_seconds: float
    duration_seconds: float
    reason: str


@dataclass(frozen=True, slots=True)
class RecordingResult:
    segment_id: RecordingSegmentId
    speaker: Speaker
    status: RecordingStatus
    offset_seconds: float
    duration_seconds: float
    manifest_failure: str | None
    gaps: tuple[RecordingGapResult, ...]


@dataclass(frozen=True, slots=True)
class StageResult:
    id: StageId
    kind: StageKind
    state: StageState
    turns: tuple[ResultTurn, ...]
    assessment: AssessmentResult | None
    recordings: tuple[RecordingResult, ...]


@dataclass(frozen=True, slots=True)
class InterviewResult:
    id: InterviewId
    candidate_name: str
    state: InterviewState
    created_at: datetime
    stages: tuple[StageResult, ...]


@dataclass(frozen=True, slots=True)
class MediaRecord:
    segment_id: RecordingSegmentId
    relative_path: str
    checksum_sha256: str
    status: RecordingStatus
