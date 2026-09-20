import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import cast

from livekit import rtc
from livekit.agents import Agent, AgentSession, room_io
from livekit.agents.voice.events import CloseEvent, CloseReason

from interview_app.adapters.fakes import FakeClock
from interview_app.adapters.livekit import LiveKitStageRuntime
from interview_app.application.ports.stage_runtime import StageLifecycleError
from interview_app.domain.models import (
    InterviewId,
    StageEventType,
    StageId,
    StageKind,
    StageRecord,
    StageStartContext,
    StageState,
)

NOW = datetime(2026, 9, 20, 16, 0, tzinfo=UTC)


class StubRoom:
    def __init__(self, sid: str) -> None:
        self.sid = _resolved(sid)


class StubSession:
    def __init__(self) -> None:
        self.started_with: tuple[Agent, rtc.Room, room_io.RoomOptions, bool, bool] | None = None
        self.shutdown_drain: bool | None = None
        self.fully_closed = False
        self._close_handler: Callable[[CloseEvent], None] | None = None

    def on(self, event: str, callback: Callable[[CloseEvent], None]) -> None:
        assert event == "close"
        self._close_handler = callback

    async def start(
        self,
        *,
        agent: Agent,
        room: rtc.Room,
        room_options: room_io.RoomOptions,
        session_host: bool,
        record: bool,
    ) -> None:
        self.started_with = (agent, room, room_options, session_host, record)

    def shutdown(self, *, drain: bool) -> None:
        self.shutdown_drain = drain
        assert self._close_handler is not None
        self._close_handler(CloseEvent(reason=CloseReason.USER_INITIATED, error=None))

    async def aclose(self) -> None:
        self.fully_closed = True


def _resolved(value: str) -> Coroutine[None, None, str]:
    async def resolve() -> str:
        return value

    return resolve()


def _context(room_sid: str = "RM_bound") -> StageStartContext:
    return StageStartContext(
        stage=StageRecord(
            id=StageId("stage-livekit"),
            interview_id=InterviewId("interview-livekit"),
            kind=StageKind.HR,
            state=StageState.ACTIVE,
            created_at=NOW,
            session_reference="session-livekit",
        ),
        room_sid=room_sid,
        candidate_identity="candidate-intended",
    )


def test_livekit_runtime_binds_candidate_and_releases_only_stage_io() -> None:
    async def exercise() -> None:
        room = StubRoom("RM_bound")
        session = StubSession()
        agent = Agent(instructions="Adapter lifecycle test only.")
        runtime = LiveKitStageRuntime(
            clock=FakeClock(NOW),
            room=cast(rtc.Room, room),
            session=cast(AgentSession[object], session),
            agent=agent,
        )

        started = await runtime.start(_context())
        assert started.type is StageEventType.STARTED
        assert session.started_with is not None
        _, bound_room, options, session_host, record = session.started_with
        assert bound_room is room
        assert options.participant_identity == "candidate-intended"
        assert options.close_on_disconnect is False
        assert options.delete_room_on_close is False
        assert session_host is False
        assert record is False

        draining = await runtime.drain()
        closed = await runtime.close()
        assert session.shutdown_drain is True
        assert session.fully_closed is True
        assert draining.type is StageEventType.DRAINING
        assert closed.type is StageEventType.CLOSED

    asyncio.run(exercise())


def test_livekit_runtime_rejects_room_mismatch_and_invalid_lifecycle() -> None:
    async def exercise() -> None:
        runtime = LiveKitStageRuntime(
            clock=FakeClock(NOW),
            room=cast(rtc.Room, StubRoom("RM_other")),
            session=cast(AgentSession[object], StubSession()),
            agent=Agent(instructions="Adapter lifecycle test only."),
        )

        try:
            await runtime.start(_context())
        except StageLifecycleError as error:
            assert "persisted interview binding" in str(error)
        else:
            raise AssertionError("A mismatched room SID must be rejected.")

        try:
            await runtime.close()
        except StageLifecycleError as error:
            assert "has not started" in str(error)
        else:
            raise AssertionError("Closing an unstarted stage must fail.")

    asyncio.run(exercise())
