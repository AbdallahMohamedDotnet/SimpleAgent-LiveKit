"""Thirty-day retention cleanup orchestration."""

from dataclasses import dataclass

from interview_app.application.ports.clock import Clock
from interview_app.application.ports.retention import ArtifactStore, RetentionStore
from interview_app.domain.models import DeletionJobState, InterviewId
from interview_app.domain.policies import RetentionPolicy


@dataclass(frozen=True, slots=True)
class CleanupReport:
    prepared: int
    deleted: tuple[InterviewId, ...]
    failed: tuple[InterviewId, ...]


class CleanupExpiredInterviews:
    """Catch up expiry, delete files first, then atomically remove database rows."""

    def __init__(
        self,
        *,
        store: RetentionStore,
        artifacts: ArtifactStore,
        clock: Clock,
        policy: RetentionPolicy | None = None,
    ) -> None:
        self._store = store
        self._artifacts = artifacts
        self._clock = clock
        self._policy = policy or RetentionPolicy()

    async def execute(self) -> CleanupReport:
        now = self._clock.utc_now()
        prepared = await self._store.prepare_expired(
            expired_at_or_before=self._policy.expired_start_cutoff(now=now),
            prepared_at=now,
        )
        deleted: list[InterviewId] = []
        failed: list[InterviewId] = []
        for job in await self._store.list_pending():
            failed_paths = await self._artifacts.delete(job.artifact_paths)
            if failed_paths:
                await self._store.record_file_failure(
                    job.interview_id,
                    failed_paths=failed_paths,
                    error="One or more owned artifacts could not be deleted.",
                )
                failed.append(job.interview_id)
                continue
            completed = await self._store.complete_deletion(
                job.interview_id,
                completed_at=self._clock.utc_now(),
            )
            if completed.state is not DeletionJobState.COMPLETE:
                raise RuntimeError("Cleanup store returned a non-complete finalized job.")
            deleted.append(job.interview_id)
        return CleanupReport(
            prepared=len(prepared),
            deleted=tuple(deleted),
            failed=tuple(failed),
        )
