"""Create and inspect a locally dispatched interview without owning voice I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from interview_app.application.interview import InvalidCandidateNameError
from interview_app.application.ports.clock import Clock
from interview_app.application.ports.interview_launch import (
    InterviewLaunchGateway,
    LaunchRequest,
    LaunchStatus,
)
from interview_app.application.ports.interview_store import InterviewStore
from interview_app.application.results import InterviewResult
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
    Speaker,
    StageKind,
)


@dataclass(frozen=True, slots=True)
class StartedInterview:
    interview: InterviewRecord
    dispatch_id: str


@dataclass(frozen=True, slots=True)
class InterviewMission:
    interview: InterviewRecord
    status: LaunchStatus
    transcript: tuple[MissionTranscriptTurn, ...]


@dataclass(frozen=True, slots=True)
class MissionTranscriptTurn:
    stage: StageKind
    speaker: Speaker
    text: str
    delivery_status: DeliveryStatus
    occurred_at: datetime


class InterviewEvidenceReader(Protocol):
    """Read only the retained interview projection needed by mission monitoring."""

    async def get_interview(
        self,
        interview_id: InterviewId,
        *,
        now: datetime,
    ) -> InterviewResult: ...


class StartInterview:
    """Allocate a room/dispatch and persist its stable interview binding."""

    def __init__(
        self,
        *,
        clock: Clock,
        interviews: InterviewStore,
        gateway: InterviewLaunchGateway,
    ) -> None:
        self._clock = clock
        self._interviews = interviews
        self._gateway = gateway

    async def execute(self, candidate_name: str) -> StartedInterview:
        normalized_name = candidate_name.strip()
        if not normalized_name:
            raise InvalidCandidateNameError("Candidate name must not be blank.")
        if len(normalized_name) > 120:
            raise InvalidCandidateNameError("Candidate name must be 120 characters or fewer.")

        identifier = InterviewId(str(uuid4()))
        room_name = f"interview-{identifier}"
        candidate_identity = f"candidate-{uuid4()}"
        binding = await self._gateway.launch(
            LaunchRequest(
                interview_id=identifier,
                room_name=room_name,
                candidate_identity=candidate_identity,
            )
        )
        interview = InterviewRecord(
            id=identifier,
            candidate_name=normalized_name,
            state=InterviewState.CREATED,
            created_at=self._clock.utc_now(),
            room_name=room_name,
            room_sid=binding.room_sid,
            candidate_identity=candidate_identity,
        )
        try:
            await self._interviews.create(interview)
        except BaseException:
            await self._gateway.cancel(room_name)
            raise
        return StartedInterview(interview=interview, dispatch_id=binding.dispatch_id)


class GetInterviewMission:
    def __init__(
        self,
        *,
        clock: Clock,
        interviews: InterviewStore,
        gateway: InterviewLaunchGateway,
        evidence: InterviewEvidenceReader,
    ) -> None:
        self._clock = clock
        self._interviews = interviews
        self._gateway = gateway
        self._evidence = evidence

    async def execute(self, interview_id: InterviewId) -> InterviewMission:
        interview = await self._interviews.get(interview_id)
        if interview.room_name is None or interview.candidate_identity is None:
            raise RuntimeError("The interview does not have a durable LiveKit binding.")
        status = await self._gateway.get_status(
            room_name=interview.room_name,
            candidate_identity=interview.candidate_identity,
        )
        result = await self._evidence.get_interview(
            interview_id,
            now=self._clock.utc_now(),
        )
        transcript = tuple(
            MissionTranscriptTurn(
                stage=stage.kind,
                speaker=turn.speaker,
                text=turn.text,
                delivery_status=turn.delivery_status,
                occurred_at=turn.occurred_at,
            )
            for stage in result.stages
            for turn in stage.turns
        )
        return InterviewMission(interview=interview, status=status, transcript=transcript)
