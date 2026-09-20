"""Interview lifecycle orchestration independent of provider SDKs."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from interview_app.application.ports.clock import Clock
from interview_app.application.ports.interview_store import InterviewStore
from interview_app.application.ports.stage_runtime import StageRuntime
from interview_app.domain.models import (
    InterviewId,
    InterviewRecord,
    InterviewState,
    StageEvent,
    StageId,
    StageKind,
    StageRecord,
    StageStartContext,
    StageState,
)


class InvalidCandidateNameError(ValueError):
    """Raised when a candidate display name is blank."""


@dataclass(frozen=True, slots=True)
class DryRunResult:
    interview: InterviewRecord
    events: tuple[StageEvent, ...]


class DryRunInterview:
    """Exercise the two-stage lifecycle using explicitly injected runtimes."""

    def __init__(
        self,
        *,
        clock: Clock,
        store: InterviewStore,
        runtimes: Mapping[StageKind, StageRuntime],
    ) -> None:
        self._clock = clock
        self._store = store
        self._runtimes = runtimes

    async def execute(self, candidate_name: str) -> DryRunResult:
        normalized_name = candidate_name.strip()
        if not normalized_name:
            raise InvalidCandidateNameError("Candidate name must not be blank.")

        interview_id = InterviewId(str(uuid4()))
        interview = InterviewRecord(
            id=interview_id,
            candidate_name=normalized_name,
            state=InterviewState.CREATED,
            created_at=self._clock.utc_now(),
        )
        await self._store.create(interview)

        events: list[StageEvent] = []
        await self._run_stage(
            interview_id,
            StageKind.HR,
            expected=InterviewState.CREATED,
            active=InterviewState.HR_ACTIVE,
            draining=InterviewState.HR_DRAINING,
            events=events,
        )
        await self._store.transition(
            interview_id,
            expected=InterviewState.HR_DRAINING,
            target=InterviewState.HANDOFF,
        )
        await self._run_stage(
            interview_id,
            StageKind.TECHNICAL,
            expected=InterviewState.HANDOFF,
            active=InterviewState.TECH_ACTIVE,
            draining=InterviewState.TECH_DRAINING,
            events=events,
        )
        completed = await self._store.transition(
            interview_id,
            expected=InterviewState.TECH_DRAINING,
            target=InterviewState.INTERVIEW_FINISHED,
        )
        return DryRunResult(interview=completed, events=tuple(events))

    async def _run_stage(
        self,
        interview_id: InterviewId,
        kind: StageKind,
        *,
        expected: InterviewState,
        active: InterviewState,
        draining: InterviewState,
        events: list[StageEvent],
    ) -> None:
        runtime = self._runtimes[kind]
        await self._store.transition(interview_id, expected=expected, target=active)
        stage = StageRecord(
            id=StageId(str(uuid4())),
            interview_id=interview_id,
            kind=kind,
            state=StageState.CREATED,
            created_at=self._clock.utc_now(),
        )
        events.append(
            await runtime.start(
                StageStartContext(
                    stage=stage,
                    room_sid=f"dry-room-{interview_id}",
                    candidate_identity=f"dry-candidate-{interview_id}",
                )
            )
        )
        await self._store.transition(interview_id, expected=active, target=draining)
        events.append(await runtime.drain())
        events.append(await runtime.close())
