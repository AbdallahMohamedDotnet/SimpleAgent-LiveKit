"""LiveKit implementation of one stage's conversational I/O lifecycle."""

import asyncio
from collections.abc import Callable
from enum import StrEnum
from uuid import uuid4

from livekit import rtc
from livekit.agents import Agent, AgentSession, room_io
from livekit.agents.voice.events import CloseEvent, UserStateChangedEvent

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
        agent: Agent | None = None,
        agent_factory: Callable[[StageStartContext], Agent] | None = None,
        transcript_bridge: LiveKitTranscriptBridge | None = None,
    ) -> None:
        if (agent is None) == (agent_factory is None):
            raise ValueError("Provide exactly one of agent or agent_factory.")
        self._clock = clock
        self._room = room
        self._session = session
        self._agent = agent
        self._agent_factory = agent_factory
        self._transcript_bridge = transcript_bridge
        self._state = _RuntimeState.NEW
        self._context: StageStartContext | None = None
        self._session_closed = asyncio.Event()
        self._candidate_answer_finished = asyncio.Event()
        self._session.on("close", self._on_session_closed)
        self._session.on("user_state_changed", self._on_user_state_changed)

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
            agent = self._agent or self._require_agent_factory()(context)
            await self._session.start(
                agent=agent,
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

    async def ask_opening_question(self) -> None:
        self._require_active()
        handle = self._session.generate_reply(
            instructions=(
                "Greet the candidate briefly, then ask the first substantive interview "
                "question. Ask exactly one concise question and wait for the answer."
            ),
            allow_interruptions=True,
        )
        await handle.wait_for_playout()
        if error := handle.exception():
            raise StageLifecycleError("LiveKit could not deliver the opening question.") from error

    async def wait_for_deadline(self, target_seconds: float) -> None:
        self._require_active()
        if target_seconds <= 0:
            raise ValueError("target_seconds must be positive.")
        await asyncio.sleep(target_seconds)
        if self._session.user_state == "speaking":
            self._candidate_answer_finished.clear()
            if self._session.user_state == "speaking":
                await self._candidate_answer_finished.wait()

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

    def _on_user_state_changed(self, event: UserStateChangedEvent) -> None:
        if event.old_state == "speaking" and event.new_state != "speaking":
            self._candidate_answer_finished.set()

    def _require_active(self) -> StageStartContext:
        context = self._require_context()
        if self._state is not _RuntimeState.ACTIVE:
            raise StageLifecycleError("The LiveKit stage is not active.")
        return context

    def _require_agent_factory(self) -> Callable[[StageStartContext], Agent]:
        if self._agent_factory is None:
            raise StageLifecycleError("No LiveKit agent factory is configured.")
        return self._agent_factory

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
