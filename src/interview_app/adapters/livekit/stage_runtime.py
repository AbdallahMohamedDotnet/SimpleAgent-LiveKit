"""LiveKit implementation of one stage's conversational I/O lifecycle."""

import asyncio
from enum import StrEnum
from uuid import uuid4

from livekit import rtc
from livekit.agents import Agent, AgentSession, room_io
from livekit.agents.voice.events import CloseEvent

from interview_app.adapters.livekit.transcripts import LiveKitTranscriptBridge
from interview_app.application.ports.clock import Clock
from interview_app.application.ports.stage_runtime import StageLifecycleError
from interview_app.domain.models import (
    EventId,
    StageEvent,
    StageEventType,
    StageStartContext,
)


class _RuntimeState(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    DRAINED = "drained"
    CLOSED = "closed"


class LiveKitStageRuntime:
    """Own exactly one AgentSession while borrowing a job-scoped Room.

    The JobContext remains the owner of ``room``. Closing this runtime drains its
    session and RoomIO, but the options explicitly prevent room deletion and do
    not treat candidate disconnect as authority to shut down the whole job.
    """

    def __init__(
        self,
        *,
        clock: Clock,
        room: rtc.Room,
        session: AgentSession[object],
        agent: Agent,
        transcript_bridge: LiveKitTranscriptBridge | None = None,
    ) -> None:
        self._clock = clock
        self._room = room
        self._session = session
        self._agent = agent
        self._transcript_bridge = transcript_bridge
        self._state = _RuntimeState.NEW
        self._context: StageStartContext | None = None
        self._session_closed = asyncio.Event()
        self._session.on("close", self._on_session_closed)

    async def start(self, context: StageStartContext) -> StageEvent:
        if self._state is not _RuntimeState.NEW:
            raise StageLifecycleError("A LiveKit stage runtime can only be started once.")

        actual_room_sid = await self._room.sid
        if actual_room_sid != context.room_sid:
            raise StageLifecycleError(
                "The connected LiveKit room does not match the persisted interview binding."
            )

        options = room_io.RoomOptions(
            participant_identity=context.candidate_identity,
            close_on_disconnect=False,
            delete_room_on_close=False,
        )
        try:
            if self._transcript_bridge is not None:
                self._transcript_bridge.attach(self._session, context.stage.id)
            await self._session.start(
                agent=self._agent,
                room=self._room,
                room_options=options,
                session_host=False,
                record=False,
            )
        except Exception as error:
            if self._transcript_bridge is not None:
                await self._transcript_bridge.flush_and_detach()
            raise StageLifecycleError("LiveKit failed to start stage I/O.") from error

        self._context = context
        self._state = _RuntimeState.ACTIVE
        return self._event(StageEventType.STARTED)

    async def drain(self) -> StageEvent:
        context = self._require_context()
        if self._state is not _RuntimeState.ACTIVE:
            raise StageLifecycleError("Only an active LiveKit stage can be drained.")

        try:
            self._session.shutdown(drain=True)
            await self._session_closed.wait()
            # LiveKit emits ``close`` before its RoomIO cleanup finishes. Waiting
            # on aclose acquires the session lifecycle lock after that cleanup,
            # providing the no-overlap barrier required before the next stage.
            await self._session.aclose()
            if self._transcript_bridge is not None:
                await self._transcript_bridge.flush_and_detach()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise StageLifecycleError("LiveKit failed while draining stage I/O.") from error

        self._state = _RuntimeState.DRAINED
        return self._event_for(context, StageEventType.DRAINING)

    async def close(self) -> StageEvent:
        context = self._require_context()
        if self._state is not _RuntimeState.DRAINED:
            raise StageLifecycleError("A LiveKit stage must finish draining before close.")

        self._state = _RuntimeState.CLOSED
        return self._event_for(context, StageEventType.CLOSED)

    def _on_session_closed(self, _: CloseEvent) -> None:
        self._session_closed.set()

    def _require_context(self) -> StageStartContext:
        if self._context is None:
            raise StageLifecycleError("The LiveKit stage has not started.")
        return self._context

    def _event(self, event_type: StageEventType) -> StageEvent:
        return self._event_for(self._require_context(), event_type)

    def _event_for(
        self,
        context: StageStartContext,
        event_type: StageEventType,
    ) -> StageEvent:
        return StageEvent(
            id=EventId(str(uuid4())),
            interview_id=context.stage.interview_id,
            stage_id=context.stage.id,
            stage_kind=context.stage.kind,
            type=event_type,
            occurred_at=self._clock.utc_now(),
        )
