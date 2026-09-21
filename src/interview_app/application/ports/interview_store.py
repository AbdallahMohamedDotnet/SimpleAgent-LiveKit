"""Interview persistence contract used by lifecycle orchestration."""

from typing import Protocol

from interview_app.domain.models import InterviewId, InterviewRecord, InterviewState


class InterviewNotFoundError(LookupError):
    """Raised when an interview ID is unknown to the store."""


class InterviewStateConflictError(RuntimeError):
    """Raised when a guarded transition observes an unexpected state."""


class ActiveInterviewExistsError(InterviewStateConflictError):
    """Raised when a new interview would break the one-active-interview rule (R03)."""

    def __init__(self, active_id: InterviewId) -> None:
        super().__init__(f"Active interview already exists: {active_id}")
        self.active_id = active_id


class InterviewStore(Protocol):
    """Persist interviews with guarded, atomic state transitions."""

    async def create(self, record: InterviewRecord) -> None: ...

    async def get(self, interview_id: InterviewId) -> InterviewRecord: ...

    async def find_active(self) -> InterviewRecord | None:
        """Return the interview that is neither finished nor incomplete, if one exists."""
        ...

    async def transition(
        self,
        interview_id: InterviewId,
        *,
        expected: InterviewState,
        target: InterviewState,
    ) -> InterviewRecord: ...
