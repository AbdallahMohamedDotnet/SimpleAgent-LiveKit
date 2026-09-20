"""Immutable domain records shared across application boundaries."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

InterviewId = NewType("InterviewId", str)
StageId = NewType("StageId", str)
TurnId = NewType("TurnId", str)
EventId = NewType("EventId", str)
SnapshotId = NewType("SnapshotId", str)
ScoreTaskId = NewType("ScoreTaskId", str)
RecordingId = NewType("RecordingId", str)
RecordingSegmentId = NewType("RecordingSegmentId", str)


class InterviewState(StrEnum):
    CREATED = "created"
    HR_ACTIVE = "hr_active"
    HR_DRAINING = "hr_draining"
    HANDOFF = "handoff"
    TECH_ACTIVE = "tech_active"
    TECH_DRAINING = "tech_draining"
    INTERVIEW_FINISHED = "interview_finished"
    INCOMPLETE = "incomplete"


class StageKind(StrEnum):
    HR = "hr"
    TECHNICAL = "technical"


class StageState(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    DRAINING = "draining"
    CLOSED = "closed"


class Speaker(StrEnum):
    CANDIDATE = "candidate"
    INTERVIEWER = "interviewer"


class DeliveryStatus(StrEnum):
    DELIVERED = "delivered"
    UNCERTAIN = "uncertain"
    NOT_DELIVERED = "not_delivered"


class ScoreTaskState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"


class RecordingStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class StageEventType(StrEnum):
    STARTED = "started"
    DRAINING = "draining"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class InterviewRecord:
    id: InterviewId
    candidate_name: str
    state: InterviewState
    created_at: datetime
    room_name: str | None = None
    room_sid: str | None = None
    candidate_identity: str | None = None


@dataclass(frozen=True, slots=True)
class StageRecord:
    id: StageId
    interview_id: InterviewId
    kind: StageKind
    state: StageState
    created_at: datetime
    session_reference: str | None = None


@dataclass(frozen=True, slots=True)
class TurnRecord:
    id: TurnId
    stage_id: StageId
    speaker: Speaker
    text: str
    is_final: bool
    delivery_status: DeliveryStatus
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class TranscriptSnapshot:
    id: SnapshotId
    stage_id: StageId
    rubric_version: str
    content_hash: str
    turn_ids: tuple[TurnId, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ScoreTaskRecord:
    id: ScoreTaskId
    snapshot_id: SnapshotId
    rubric_version: str
    state: ScoreTaskState
    attempts: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    created_at: datetime
    completed_at: datetime | None = None
    failure: str | None = None


@dataclass(frozen=True, slots=True)
class RecordingGap:
    offset_seconds: float
    duration_seconds: float
    reason: str


@dataclass(frozen=True, slots=True)
class RecordingSegment:
    id: RecordingSegmentId
    recording_id: RecordingId
    stage_id: StageId
    speaker: Speaker
    relative_path: str
    offset_seconds: float
    duration_seconds: float
    checksum_sha256: str
    status: RecordingStatus
    gaps: tuple[RecordingGap, ...]


@dataclass(frozen=True, slots=True)
class RecordingManifest:
    id: RecordingId
    interview_id: InterviewId
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    started_at: datetime
    completed_at: datetime
    status: RecordingStatus
    failure: str | None
    segments: tuple[RecordingSegment, ...]


@dataclass(frozen=True, slots=True)
class StageEvent:
    id: EventId
    interview_id: InterviewId
    stage_id: StageId
    stage_kind: StageKind
    type: StageEventType
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class AttributedTurn:
    id: TurnId
    speaker: Speaker
    text: str
    delivery_status: DeliveryStatus


@dataclass(frozen=True, slots=True)
class HandoffPayload:
    interview_id: InterviewId
    candidate_name: str
    candidate_identity: str
    source_stage_id: StageId
    snapshot_id: SnapshotId
    snapshot_hash: str
    turns: tuple[AttributedTurn, ...]
    completed_stage: StageKind


@dataclass(frozen=True, slots=True)
class StageStartContext:
    stage: StageRecord
    room_sid: str
    candidate_identity: str
    handoff: HandoffPayload | None = None
