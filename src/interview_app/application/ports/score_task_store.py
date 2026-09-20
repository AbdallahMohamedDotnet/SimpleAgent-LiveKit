"""Durable assessment queue contract."""

from datetime import datetime, timedelta
from typing import Protocol

from interview_app.domain.models import ScoreTaskId, ScoreTaskRecord


class ScoreTaskLeaseError(RuntimeError):
    """Raised when a worker no longer owns a task lease."""


class ScoreTaskStore(Protocol):
    async def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> ScoreTaskRecord | None: ...

    async def complete(
        self,
        task_id: ScoreTaskId,
        *,
        worker_id: str,
        completed_at: datetime,
    ) -> ScoreTaskRecord: ...
