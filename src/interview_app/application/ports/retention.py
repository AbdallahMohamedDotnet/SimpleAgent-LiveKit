"""Retention persistence and owned-artifact contracts."""

from datetime import datetime
from typing import Protocol

from interview_app.domain.models import DeletionJob, InterviewId


class RetentionStore(Protocol):
    async def prepare_expired(
        self,
        *,
        expired_at_or_before: datetime,
        prepared_at: datetime,
    ) -> tuple[DeletionJob, ...]: ...

    async def list_pending(self) -> tuple[DeletionJob, ...]: ...

    async def record_file_failure(
        self,
        interview_id: InterviewId,
        *,
        failed_paths: tuple[str, ...],
        error: str,
    ) -> DeletionJob: ...

    async def complete_deletion(
        self,
        interview_id: InterviewId,
        *,
        completed_at: datetime,
    ) -> DeletionJob: ...


class ArtifactStore(Protocol):
    async def delete(self, relative_paths: tuple[str, ...]) -> tuple[str, ...]:
        """Delete owned artifacts and return paths that could not be removed."""
        ...
