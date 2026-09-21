"""Ordered, idempotent transition between distinct stage runtimes."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from interview_app.application.ports.clock import Clock
from interview_app.application.ports.interview_store import InterviewNotFoundError, InterviewStore
from interview_app.application.ports.stage_runtime import StageRuntime
from interview_app.application.ports.transcript_store import TranscriptStore
from interview_app.domain.models import (
    AttributedTurn,
    HandoffPayload,
    InterviewId,
    InterviewRecord,
    InterviewState,
    ScoreTaskRecord,
    StageEvent,
    StageId,
    StageKind,
    StageRecord,
    StageStartContext,
    StageState,
    TranscriptSnapshot,
)


class HandoffConfigurationError(ValueError):
    """Raised when durable room/candidate binding information is missing."""


@dataclass(frozen=True, slots=True)
class HandoffResult:
    payload: HandoffPayload
    snapshot: TranscriptSnapshot
    score_task: ScoreTaskRecord
    technical_stage: StageRecord
    events: tuple[StageEvent, ...]


@dataclass(frozen=True, slots=True)
class InterviewCompletion:
    snapshot: TranscriptSnapshot
    score_task: ScoreTaskRecord
    events: tuple[StageEvent, ...]


class TwoStageHandoffController:
    """Own stage transitions while runtimes own only their individual I/O."""

    def __init__(
        self,
        *,
        clock: Clock,
        interviews: InterviewStore,
        transcripts: TranscriptStore,
        runtimes: Mapping[StageKind, StageRuntime],
        hr_rubric_version: str,
        technical_rubric_version: str = "technical-v1",
    ) -> None:
        if runtimes[StageKind.HR] is runtimes[StageKind.TECHNICAL]:
            raise HandoffConfigurationError("HR and technical stages require distinct runtimes.")
        self._clock = clock
        self._interviews = interviews
        self._transcripts = transcripts
        self._runtimes = runtimes
        self._hr_rubric_version = hr_rubric_version
        self._technical_rubric_version = technical_rubric_version
        self._hr_stage: StageRecord | None = None
        self._technical_stage: StageRecord | None = None
        self._result: HandoffResult | None = None
        self._completion: InterviewCompletion | None = None
        self._handoff_lock = asyncio.Lock()

    async def begin(self, interview: InterviewRecord) -> StageRecord:
        room_sid, candidate_identity = self._binding(interview)
        try:
            persisted = await self._interviews.get(interview.id)
        except InterviewNotFoundError:
            await self._interviews.create(interview)
        else:
            if persisted != interview:
                raise HandoffConfigurationError(
                    "The dispatched interview does not match its durable binding."
                )
        await self._interviews.transition(
            interview.id,
            expected=InterviewState.CREATED,
            target=InterviewState.HR_ACTIVE,
        )
        stage = StageRecord(
            id=StageId(str(uuid4())),
            interview_id=interview.id,
            kind=StageKind.HR,
            state=StageState.ACTIVE,
            created_at=self._clock.utc_now(),
            session_reference=str(uuid4()),
        )
        await self._transcripts.create_stage(stage)
        event = await self._runtimes[StageKind.HR].start(
            StageStartContext(
                stage=stage,
                room_sid=room_sid,
                candidate_identity=candidate_identity,
            )
        )
        await self._transcripts.append_event(event)
        self._hr_stage = stage
        return stage

    async def handoff(self, interview_id: InterviewId) -> HandoffResult:
        async with self._handoff_lock:
            if self._result is not None:
                return self._result
            if self._hr_stage is None or self._hr_stage.interview_id != interview_id:
                raise HandoffConfigurationError("The HR stage has not started for this interview.")
            interview = await self._interviews.get(interview_id)
            room_sid, candidate_identity = self._binding(interview)
            hr_stage = self._hr_stage
            events: list[StageEvent] = []

            await self._interviews.transition(
                interview_id,
                expected=InterviewState.HR_ACTIVE,
                target=InterviewState.HR_DRAINING,
            )
            await self._transcripts.transition_stage(
                hr_stage.id,
                expected=StageState.ACTIVE,
                target=StageState.DRAINING,
            )
            events.append(await self._runtimes[StageKind.HR].drain())
            await self._transcripts.append_event(events[-1])
            events.append(await self._runtimes[StageKind.HR].close())
            await self._transcripts.append_event(events[-1])
            await self._transcripts.transition_stage(
                hr_stage.id,
                expected=StageState.DRAINING,
                target=StageState.CLOSED,
            )

            snapshot, score_task = await self._transcripts.finalize_snapshot_and_enqueue(
                hr_stage.id,
                rubric_version=self._hr_rubric_version,
                created_at=self._clock.utc_now(),
            )
            final_turns = await self._transcripts.list_turns(hr_stage.id, final_only=True)
            payload = HandoffPayload(
                interview_id=interview.id,
                candidate_name=interview.candidate_name,
                candidate_identity=candidate_identity,
                source_stage_id=hr_stage.id,
                snapshot_id=snapshot.id,
                snapshot_hash=snapshot.content_hash,
                turns=tuple(
                    AttributedTurn(
                        id=turn.id,
                        speaker=turn.speaker,
                        text=turn.text,
                        delivery_status=turn.delivery_status,
                    )
                    for turn in final_turns
                ),
                completed_stage=StageKind.HR,
            )
            await self._interviews.transition(
                interview_id,
                expected=InterviewState.HR_DRAINING,
                target=InterviewState.HANDOFF,
            )
            technical_stage = StageRecord(
                id=StageId(str(uuid4())),
                interview_id=interview.id,
                kind=StageKind.TECHNICAL,
                state=StageState.ACTIVE,
                created_at=self._clock.utc_now(),
                session_reference=str(uuid4()),
            )
            await self._transcripts.create_stage(technical_stage)
            events.append(
                await self._runtimes[StageKind.TECHNICAL].start(
                    StageStartContext(
                        stage=technical_stage,
                        room_sid=room_sid,
                        candidate_identity=candidate_identity,
                        handoff=payload,
                    )
                )
            )
            await self._transcripts.append_event(events[-1])
            await self._interviews.transition(
                interview_id,
                expected=InterviewState.HANDOFF,
                target=InterviewState.TECH_ACTIVE,
            )
            self._result = HandoffResult(
                payload=payload,
                snapshot=snapshot,
                score_task=score_task,
                technical_stage=technical_stage,
                events=tuple(events),
            )
            self._technical_stage = technical_stage
            return self._result

    async def finish(self, interview_id: InterviewId) -> InterviewCompletion:
        """Close the technical stage and durably enqueue its independent score."""
        async with self._handoff_lock:
            if self._completion is not None:
                return self._completion
            if self._technical_stage is None or self._technical_stage.interview_id != interview_id:
                raise HandoffConfigurationError(
                    "The technical stage has not started for this interview."
                )
            technical_stage = self._technical_stage
            events: list[StageEvent] = []
            await self._interviews.transition(
                interview_id,
                expected=InterviewState.TECH_ACTIVE,
                target=InterviewState.TECH_DRAINING,
            )
            await self._transcripts.transition_stage(
                technical_stage.id,
                expected=StageState.ACTIVE,
                target=StageState.DRAINING,
            )
            events.append(await self._runtimes[StageKind.TECHNICAL].drain())
            await self._transcripts.append_event(events[-1])
            events.append(await self._runtimes[StageKind.TECHNICAL].close())
            await self._transcripts.append_event(events[-1])
            await self._transcripts.transition_stage(
                technical_stage.id,
                expected=StageState.DRAINING,
                target=StageState.CLOSED,
            )
            snapshot, score_task = await self._transcripts.finalize_snapshot_and_enqueue(
                technical_stage.id,
                rubric_version=self._technical_rubric_version,
                created_at=self._clock.utc_now(),
            )
            await self._interviews.transition(
                interview_id,
                expected=InterviewState.TECH_DRAINING,
                target=InterviewState.INTERVIEW_FINISHED,
            )
            self._completion = InterviewCompletion(
                snapshot=snapshot,
                score_task=score_task,
                events=tuple(events),
            )
            return self._completion

    @staticmethod
    def _binding(interview: InterviewRecord) -> tuple[str, str]:
        if not interview.room_sid or not interview.candidate_identity:
            raise HandoffConfigurationError(
                "Room SID and candidate identity are required for a stage runtime."
            )
        return interview.room_sid, interview.candidate_identity
