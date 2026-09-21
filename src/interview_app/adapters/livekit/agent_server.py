"""Local ROOM Agent Server wiring for the two-stage interview job."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from livekit.agents import AgentServer, AgentSession, JobContext

from interview_app.adapters.clock import SystemClock
from interview_app.adapters.livekit.interviewers import (
    HrInterviewerAgent,
    TechnicalInterviewerAgent,
)
from interview_app.adapters.livekit.stage_runtime import LiveKitStageRuntime
from interview_app.adapters.livekit.transcripts import LiveKitTranscriptBridge
from interview_app.adapters.providers.voice import VoiceProviderBundle, build_voice_providers
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteTranscriptStore,
)
from interview_app.application.handoff import TwoStageHandoffController
from interview_app.application.live_interview import LiveInterviewCoordinator
from interview_app.application.ports.interview_store import (
    InterviewNotFoundError,
    InterviewStore,
)
from interview_app.domain.models import (
    HandoffPayload,
    InterviewId,
    InterviewRecord,
    StageKind,
    StageStartContext,
)
from interview_app.resources.rubrics import HR_RUBRIC_V1, TECHNICAL_RUBRIC_V1
from interview_app.settings import Settings


class InvalidJobMetadataError(ValueError):
    """Raised when an untrusted dispatch cannot be bound to a durable interview."""


@dataclass(frozen=True, slots=True)
class InterviewJobMetadata:
    interview_id: InterviewId
    candidate_identity: str

    @classmethod
    def parse(cls, raw: str) -> InterviewJobMetadata:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise InvalidJobMetadataError("Dispatch metadata must be valid JSON.") from error
        if not isinstance(value, dict):
            raise InvalidJobMetadataError("Dispatch metadata must be a JSON object.")
        interview_id = value.get("interview_id")
        candidate_identity = value.get("candidate_identity")
        if not isinstance(interview_id, str) or not interview_id.strip():
            raise InvalidJobMetadataError("Dispatch metadata has no interview_id.")
        if not isinstance(candidate_identity, str) or not candidate_identity.strip():
            raise InvalidJobMetadataError("Dispatch metadata has no candidate_identity.")
        return cls(
            interview_id=InterviewId(interview_id.strip()),
            candidate_identity=candidate_identity.strip(),
        )


@dataclass(frozen=True, slots=True)
class AgentServerConfiguration:
    settings: Settings
    sqlite_path: Path
    agent_name: str


class LiveKitInterviewJob:
    """Compose one dispatched job while the JobContext retains room ownership."""

    def __init__(self, configuration: AgentServerConfiguration) -> None:
        self._configuration = configuration

    async def execute(self, context: JobContext) -> None:
        metadata = InterviewJobMetadata.parse(context.job.metadata)
        database = SqliteDatabase(self._configuration.sqlite_path)
        await database.migrate()
        interviews = SqliteInterviewStore(database)
        transcripts = SqliteTranscriptStore(database)
        interview = await _wait_for_dispatched_interview(interviews, metadata.interview_id)
        if interview.candidate_identity != metadata.candidate_identity:
            raise InvalidJobMetadataError(
                "Dispatch candidate identity does not match durable interview data."
            )
        if interview.room_name != context.job.room.name:
            raise InvalidJobMetadataError("Dispatch room does not match durable interview data.")

        await context.connect()
        room_sid = await context.room.sid
        if interview.room_sid != room_sid:
            raise InvalidJobMetadataError(
                "Connected room SID does not match durable interview data."
            )
        await context.wait_for_participant(identity=metadata.candidate_identity)

        providers = build_voice_providers(self._configuration.settings)
        try:
            await self._run_conversation(
                context=context,
                interview=interview,
                interviews=interviews,
                transcripts=transcripts,
                providers=providers,
            )
        finally:
            await _close_providers(providers)

    async def _run_conversation(
        self,
        *,
        context: JobContext,
        interview: InterviewRecord,
        interviews: SqliteInterviewStore,
        transcripts: SqliteTranscriptStore,
        providers: VoiceProviderBundle,
    ) -> None:
        clock = SystemClock()
        hr_session: AgentSession[object] = AgentSession(
            stt=providers.stt,
            llm=providers.llm,
            tts=providers.hr_tts,
            allow_interruptions=True,
            user_away_timeout=None,
        )
        technical_session: AgentSession[object] = AgentSession(
            stt=providers.stt,
            llm=providers.llm,
            tts=providers.technical_tts,
            allow_interruptions=True,
            user_away_timeout=None,
        )
        hr_runtime = LiveKitStageRuntime(
            clock=clock,
            room=context.room,
            session=hr_session,
            agent=HrInterviewerAgent(),
            transcript_bridge=LiveKitTranscriptBridge(clock=clock, transcripts=transcripts),
        )

        def technical_agent(stage_context: StageStartContext) -> TechnicalInterviewerAgent:
            handoff = stage_context.handoff
            if not isinstance(handoff, HandoffPayload):
                raise InvalidJobMetadataError("Technical stage requires a frozen HR handoff.")
            return TechnicalInterviewerAgent(handoff)

        technical_runtime = LiveKitStageRuntime(
            clock=clock,
            room=context.room,
            session=technical_session,
            agent_factory=technical_agent,
            transcript_bridge=LiveKitTranscriptBridge(clock=clock, transcripts=transcripts),
        )
        controller = TwoStageHandoffController(
            clock=clock,
            interviews=interviews,
            transcripts=transcripts,
            runtimes={StageKind.HR: hr_runtime, StageKind.TECHNICAL: technical_runtime},
            hr_rubric_version=HR_RUBRIC_V1.version,
            technical_rubric_version=TECHNICAL_RUBRIC_V1.version,
        )
        coordinator = LiveInterviewCoordinator(
            controller=controller,
            conversations={StageKind.HR: hr_runtime, StageKind.TECHNICAL: technical_runtime},
            hr_target_seconds=self._configuration.settings.hr_target_seconds,
            technical_target_seconds=self._configuration.settings.tech_target_seconds,
        )
        await coordinator.execute(interview)


async def _close_providers(providers: VoiceProviderBundle) -> None:
    await providers.llm.aclose()
    await providers.stt.aclose()
    await providers.hr_tts.aclose()
    await providers.technical_tts.aclose()


async def _wait_for_dispatched_interview(
    interviews: InterviewStore,
    interview_id: InterviewId,
    *,
    attempts: int = 20,
    delay_seconds: float = 0.1,
) -> InterviewRecord:
    """Bridge the short room-dispatch/database-commit ordering window."""
    if attempts < 1 or delay_seconds < 0:
        raise ValueError("Dispatch lookup retry settings are invalid.")
    for attempt in range(attempts):
        try:
            return await interviews.get(interview_id)
        except InterviewNotFoundError:
            if attempt + 1 == attempts:
                raise
            await asyncio.sleep(delay_seconds)
    raise RuntimeError("Unreachable dispatch lookup state.")


def build_agent_server(configuration: AgentServerConfiguration) -> AgentServer:
    settings = configuration.settings
    server = AgentServer(
        ws_url=settings.livekit_url,
        api_key=settings.livekit_api_key.reveal(),
        api_secret=settings.livekit_api_secret.reveal(),
    )
    job = LiveKitInterviewJob(configuration)
    server.rtc_session(job.execute, agent_name=configuration.agent_name)
    return server
