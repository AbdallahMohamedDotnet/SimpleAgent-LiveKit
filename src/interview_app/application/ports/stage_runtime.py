"""One-stage conversational runtime contract."""

from typing import Protocol

from interview_app.domain.models import StageEvent, StageStartContext


class StageLifecycleError(RuntimeError):
    """Raised for an invalid stage runtime lifecycle operation."""


class StageRuntime(Protocol):
    """Own one stage's I/O lifecycle, without owning the room or whole job.

    Implementations must be started once, drained before close, and remain closed.
    Closing a stage must not disconnect the shared room connection.
    """

    async def start(self, context: StageStartContext) -> StageEvent: ...

    async def drain(self) -> StageEvent: ...

    async def close(self) -> StageEvent: ...
