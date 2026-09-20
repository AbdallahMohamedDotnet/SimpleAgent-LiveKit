"""Deterministic offline adapters that obey production-facing contracts."""

from asyncio import Event
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from interview_app.application.ports.clock import Clock
from interview_app.application.ports.interview_store import (
    InterviewNotFoundError,
    InterviewStateConflictError,
)
from interview_app.application.ports.score_task_store import ScoreTaskStore
from interview_app.application.ports.stage_runtime import StageLifecycleError
from interview_app.domain.models import (
    EventId,
    InterviewId,
    InterviewRecord,
    InterviewState,
    ScoreTaskRecord,
    StageEvent,
    StageEventType,
    StageRecord,
    StageStartContext,
)


class FakeClock:
    def __init__(self, now: datetime | None = None, monotonic: float = 0.0) -> None:
        self._now = now or datetime(2026, 1, 1, tzinfo=UTC)
        if self._now.tzinfo is None or self._now.utcoffset() is None:
            raise ValueError("FakeClock requires a timezone-aware datetime.")
        self._monotonic = monotonic

    def monotonic(self) -> float:
        return self._monotonic

    def utc_now(self) -> datetime:
        return self._now.astimezone(UTC)

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("Clock cannot move backwards.")
        self._monotonic += seconds
        self._now += timedelta(seconds=seconds)


class InMemoryInterviewStore:
    def __init__(self) -> None:
        self._records: dict[InterviewId, InterviewRecord] = {}

    async def create(self, record: InterviewRecord) -> None:
        if record.id in self._records:
            raise InterviewStateConflictError(f"Interview already exists: {record.id}")
        if record.state not in {
            InterviewState.INTERVIEW_FINISHED,
            InterviewState.INCOMPLETE,
        } and any(
            existing.state not in {InterviewState.INTERVIEW_FINISHED, InterviewState.INCOMPLETE}
            for existing in self._records.values()
        ):
            raise InterviewStateConflictError("An active interview already exists.")
        self._records[record.id] = record

    async def get(self, interview_id: InterviewId) -> InterviewRecord:
        try:
            return self._records[interview_id]
        except KeyError as error:
            raise InterviewNotFoundError(f"Unknown interview: {interview_id}") from error

    async def transition(
        self,
        interview_id: InterviewId,
        *,
        expected: InterviewState,
        target: InterviewState,
    ) -> InterviewRecord:
        current = await self.get(interview_id)
        if current.state is not expected:
            raise InterviewStateConflictError(
                f"Expected {expected.value}, found {current.state.value}."
            )
        updated = replace(current, state=target)
        self._records[interview_id] = updated
        return updated


class FakeStageRuntime:
    """A one-use runtime that models required start/drain/close ordering."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self._stage: StageRecord | None = None
        self._drained = False
        self._closed = False
        self.start_context: StageStartContext | None = None

    async def start(self, context: StageStartContext) -> StageEvent:
        if self._stage is not None:
            raise StageLifecycleError("Stage runtime may only be started once.")
        self.start_context = context
        self._stage = context.stage
        return self._event(StageEventType.STARTED)

    async def drain(self) -> StageEvent:
        self._require_started()
        if self._drained:
            raise StageLifecycleError("Stage runtime is already drained.")
        if self._closed:
            raise StageLifecycleError("Closed stage runtime cannot be drained.")
        self._drained = True
        return self._event(StageEventType.DRAINING)

    async def close(self) -> StageEvent:
        self._require_started()
        if not self._drained:
            raise StageLifecycleError("Stage runtime must be drained before close.")
        if self._closed:
            raise StageLifecycleError("Stage runtime is already closed.")
        self._closed = True
        return self._event(StageEventType.CLOSED)

    def _require_started(self) -> None:
        if self._stage is None:
            raise StageLifecycleError("Stage runtime has not been started.")

    def _event(self, event_type: StageEventType) -> StageEvent:
        if self._stage is None:
            raise StageLifecycleError("Stage runtime has not been started.")
        return StageEvent(
            id=EventId(str(uuid4())),
            interview_id=self._stage.interview_id,
            stage_id=self._stage.id,
            stage_kind=self._stage.kind,
            type=event_type,
            occurred_at=self._clock.utc_now(),
        )


class FakeScoreConsumer:
    """Claim one durable task and optionally wait, without touching room media."""

    def __init__(
        self,
        *,
        store: ScoreTaskStore,
        clock: Clock,
        worker_id: str = "fake-score-worker",
        lease_duration: timedelta = timedelta(minutes=5),
        release: Event | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._worker_id = worker_id
        self._lease_duration = lease_duration
        self._release = release
        self.claimed = Event()

    async def run_one(self) -> ScoreTaskRecord | None:
        task = await self._store.claim_next(
            worker_id=self._worker_id,
            now=self._clock.utc_now(),
            lease_duration=self._lease_duration,
        )
        if task is None:
            return None
        self.claimed.set()
        if self._release is not None:
            await self._release.wait()
        return await self._store.complete(
            task.id,
            worker_id=self._worker_id,
            completed_at=self._clock.utc_now(),
        )
