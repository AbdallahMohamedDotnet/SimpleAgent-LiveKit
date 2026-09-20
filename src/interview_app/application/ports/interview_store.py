"""Interview persistence contract used by lifecycle orchestration."""

from typing import Protocol

from interview_app.domain.models import InterviewId, InterviewRecord, InterviewState


class InterviewNotFoundError(LookupError):
    """Raised when an interview ID is unknown to the store."""


class InterviewStateConflictError(RuntimeError):
    """Raised when a guarded transition observes an unexpected state."""


class InterviewStore(Protocol):
    """Persist interviews with guarded, atomic state transitions."""

    async def create(self, record: InterviewRecord) -> None: ...

    async def get(self, interview_id: InterviewId) -> InterviewRecord: ...

    async def transition(
        self,
        interview_id: InterviewId,
        *,
        expected: InterviewState,
        target: InterviewState,
    ) -> InterviewRecord: ...
