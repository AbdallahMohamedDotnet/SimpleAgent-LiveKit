"""Durable conversation evidence and snapshot contract."""

from datetime import datetime
from typing import Protocol

from interview_app.domain.models import (
    ScoreTaskRecord,
    StageEvent,
    StageId,
    StageRecord,
    StageState,
    TranscriptSnapshot,
    TurnRecord,
)


class EvidenceConflictError(RuntimeError):
    """Raised when an idempotency key is reused for different evidence."""


class TranscriptStore(Protocol):
    """Persist stage evidence without exposing database or transaction details."""

    async def create_stage(self, stage: StageRecord) -> None: ...

    async def transition_stage(
        self, stage_id: StageId, *, expected: StageState, target: StageState
    ) -> StageRecord: ...

    async def append_event(self, event: StageEvent) -> bool: ...

    async def append_turn(self, turn: TurnRecord) -> bool:
        """Persist a turn, returning False for an identical duplicate."""
        ...

    async def list_turns(
        self, stage_id: StageId, *, final_only: bool
    ) -> tuple[TurnRecord, ...]: ...

    async def finalize_snapshot_and_enqueue(
        self,
        stage_id: StageId,
        *,
        rubric_version: str,
        created_at: datetime,
    ) -> tuple[TranscriptSnapshot, ScoreTaskRecord]:
        """Freeze final turns and enqueue their score task in one transaction."""
        ...
