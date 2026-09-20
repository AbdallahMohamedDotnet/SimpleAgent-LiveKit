"""Recovery coordination and startup reconciliation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Protocol
from uuid import uuid4

from interview_app.application.ports.clock import Clock
from interview_app.application.ports.recovery_store import RecoveryStore
from interview_app.domain.models import (
    ConnectionAttempt,
    ConnectionAttemptId,
    InterviewId,
    InterviewState,
    RecordingSegmentId,
    RecoveryCheckpoint,
    TurnId,
)


class TransientRecoveryError(RuntimeError):
    """A reconnect attempt may be retried inside the current recovery budget."""


class PermanentRecoveryError(RuntimeError):
    """A configuration or credential failure must fail without retrying."""


@dataclass(frozen=True, slots=True)
class ReconnectResult:
    room_sid: str
    recording_segment_id: RecordingSegmentId | None = None


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    resumed: bool
    checkpoint: RecoveryCheckpoint
    reask_question_turn_id: TurnId | None
    incomplete_reason: str | None


class Reconnector(Protocol):
    async def reconnect(self, checkpoint: RecoveryCheckpoint) -> ReconnectResult: ...


type Sleep = Callable[[float], Awaitable[None]]


class RecoverInterview:
    """Retry one incident against one fixed 120-second wall-clock deadline."""

    def __init__(
        self,
        *,
        store: RecoveryStore,
        clock: Clock,
        reconnector: Reconnector,
        sleep: Sleep,
        budget: timedelta = timedelta(seconds=120),
    ) -> None:
        if budget != timedelta(seconds=120):
            raise ValueError("The recovery budget is fixed at 120 seconds.")
        self._store = store
        self._clock = clock
        self._reconnector = reconnector
        self._sleep = sleep
        self._budget = budget

    async def execute(self, checkpoint: RecoveryCheckpoint) -> RecoveryOutcome:
        if checkpoint.recovery_started_at is None and checkpoint.recovery_deadline_at is None:
            started_at = self._clock.utc_now()
            recovering = replace(
                checkpoint,
                recovery_started_at=started_at,
                recovery_deadline_at=started_at + self._budget,
                recovery_attempts=0,
                updated_at=started_at,
            )
            recovering = await self._store.enter_recovery(
                recovering,
                expected=checkpoint.resumable_state,
            )
        elif (
            checkpoint.recovery_started_at is not None
            and checkpoint.recovery_deadline_at is not None
        ):
            # A restarted process continues the persisted incident and must not
            # grant a fresh 120-second budget.
            recovering = checkpoint
        else:
            raise ValueError("Persisted recovery timestamps must be both set or both clear.")

        while True:
            now = self._clock.utc_now()
            deadline = recovering.recovery_deadline_at
            if deadline is None or now >= deadline:
                return await self._incomplete(recovering, "Recovery deadline exhausted.")
            attempt_number = recovering.recovery_attempts + 1
            try:
                result = await self._reconnector.reconnect(recovering)
            except PermanentRecoveryError as error:
                await self._record_attempt(recovering, succeeded=False, failure=str(error))
                return await self._incomplete(recovering, f"Permanent recovery failure: {error}")
            except TransientRecoveryError as error:
                await self._record_attempt(recovering, succeeded=False, failure=str(error))
                recovering = replace(
                    recovering,
                    recovery_attempts=attempt_number,
                    updated_at=self._clock.utc_now(),
                )
                await self._store.save_checkpoint(recovering)
                remaining = max(
                    0.0,
                    (deadline - self._clock.utc_now()).total_seconds(),
                )
                delay = min(10.0, float(2 ** (attempt_number - 1)), remaining)
                if delay <= 0:
                    return await self._incomplete(recovering, "Recovery deadline exhausted.")
                await self._sleep(delay)
                continue

            await self._store.record_connection_attempt(
                ConnectionAttempt(
                    id=ConnectionAttemptId(str(uuid4())),
                    interview_id=recovering.interview_id,
                    previous_room_sid=recovering.room_sid,
                    connected_room_sid=result.room_sid,
                    attempted_at=self._clock.utc_now(),
                    succeeded=True,
                    failure=None,
                )
            )
            resumed = replace(
                recovering,
                room_sid=result.room_sid,
                active_recording_segment_id=result.recording_segment_id,
                recovery_started_at=None,
                recovery_deadline_at=None,
                recovery_attempts=attempt_number,
                updated_at=self._clock.utc_now(),
            )
            resumed = await self._store.resume(resumed)
            return RecoveryOutcome(
                resumed=True,
                checkpoint=resumed,
                reask_question_turn_id=resumed.interrupted_question_turn_id,
                incomplete_reason=None,
            )

    async def _record_attempt(
        self,
        checkpoint: RecoveryCheckpoint,
        *,
        succeeded: bool,
        failure: str | None,
    ) -> None:
        await self._store.record_connection_attempt(
            ConnectionAttempt(
                id=ConnectionAttemptId(str(uuid4())),
                interview_id=checkpoint.interview_id,
                previous_room_sid=checkpoint.room_sid,
                connected_room_sid=None,
                attempted_at=self._clock.utc_now(),
                succeeded=succeeded,
                failure=failure,
            )
        )

    async def _incomplete(
        self,
        checkpoint: RecoveryCheckpoint,
        reason: str,
    ) -> RecoveryOutcome:
        await self._store.mark_incomplete(
            checkpoint.interview_id,
            reason=reason,
            at=self._clock.utc_now(),
        )
        return RecoveryOutcome(
            resumed=False,
            checkpoint=checkpoint,
            reask_question_turn_id=None,
            incomplete_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    resumable: tuple[RecoveryCheckpoint, ...]
    marked_incomplete: tuple[InterviewId, ...]


class ReconcileInterruptedInterviews:
    """Convert process-interrupted active states into honest recovery decisions."""

    def __init__(self, *, store: RecoveryStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    async def execute(self) -> ReconciliationResult:
        now = self._clock.utc_now()
        resumable: list[RecoveryCheckpoint] = []
        incomplete: list[InterviewId] = []
        for interrupted in await self._store.list_interrupted():
            checkpoint = interrupted.checkpoint
            if checkpoint is None:
                await self._store.mark_incomplete(
                    interrupted.interview.id,
                    reason="Interrupted process had no durable recovery checkpoint.",
                    at=now,
                )
                incomplete.append(interrupted.interview.id)
                continue
            if (
                interrupted.interview.state is InterviewState.RECOVERING
                and checkpoint.recovery_deadline_at is not None
                and now >= checkpoint.recovery_deadline_at
            ):
                await self._store.mark_incomplete(
                    interrupted.interview.id,
                    reason="Persisted recovery deadline expired while the process was offline.",
                    at=now,
                )
                incomplete.append(interrupted.interview.id)
                continue
            resumable.append(checkpoint)
        return ReconciliationResult(
            resumable=tuple(resumable),
            marked_incomplete=tuple(incomplete),
        )
