"""Durable assessment queue contract."""

from datetime import datetime, timedelta
from typing import Protocol

from interview_app.domain.models import ScoreTaskId, ScoreTaskRecord
from interview_app.domain.scoring import AssessmentTaskInput, StageAssessment, StageScoreRecord


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

    async def load_input(self, task_id: ScoreTaskId) -> AssessmentTaskInput: ...

    async def renew(
        self,
        task_id: ScoreTaskId,
        *,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> ScoreTaskRecord: ...

    async def complete_with_result(
        self,
        task_id: ScoreTaskId,
        *,
        worker_id: str,
        completed_at: datetime,
        model: str,
        assessment: StageAssessment,
        summary: str | None,
    ) -> StageScoreRecord: ...

    async def fail(
        self,
        task_id: ScoreTaskId,
        *,
        worker_id: str,
        failed_at: datetime,
        failure: str,
        retry_at: datetime | None,
    ) -> ScoreTaskRecord: ...

    async def get_result(self, task_id: ScoreTaskId) -> StageScoreRecord | None: ...
