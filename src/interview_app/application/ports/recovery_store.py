"""Durable recovery checkpoint and reconciliation contract."""

from datetime import datetime
from typing import Protocol

from interview_app.domain.models import (
    ConnectionAttempt,
    InterruptedInterview,
    InterviewId,
    InterviewState,
    RecoveryCheckpoint,
)


class RecoveryStateError(RuntimeError):
    """Raised when durable recovery state cannot make the requested transition."""


class RecoveryStore(Protocol):
    async def save_checkpoint(self, checkpoint: RecoveryCheckpoint) -> None: ...

    async def get_checkpoint(self, interview_id: InterviewId) -> RecoveryCheckpoint | None: ...

    async def enter_recovery(
        self,
        checkpoint: RecoveryCheckpoint,
        *,
        expected: InterviewState,
    ) -> RecoveryCheckpoint: ...

    async def record_connection_attempt(self, attempt: ConnectionAttempt) -> None: ...

    async def resume(self, checkpoint: RecoveryCheckpoint) -> RecoveryCheckpoint: ...

    async def mark_incomplete(
        self,
        interview_id: InterviewId,
        *,
        reason: str,
        at: datetime,
    ) -> None: ...

    async def list_interrupted(self) -> tuple[InterruptedInterview, ...]: ...
