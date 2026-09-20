import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from livekit.agents import AgentSession
from livekit.agents.llm import ChatMessage
from livekit.agents.voice.events import ConversationItemAddedEvent, UserInputTranscribedEvent

from interview_app.adapters.fakes import FakeClock
from interview_app.adapters.livekit import LiveKitTranscriptBridge
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteTranscriptStore,
)
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
    Speaker,
    StageId,
    StageKind,
    StageRecord,
    StageState,
)

NOW = datetime(2026, 9, 20, 17, 0, tzinfo=UTC)


class EventSession:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[object], None]] = {}

    def on(self, event: str, callback: Callable[[object], None]) -> None:
        self.handlers[event] = callback

    def off(self, event: str, callback: Callable[[object], None]) -> None:
        assert self.handlers[event] == callback
        del self.handlers[event]

    def emit(self, event: str, payload: object) -> None:
        self.handlers[event](payload)


def test_livekit_bridge_persists_only_final_attributed_evidence(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "transcripts.sqlite3")
        await database.migrate()
        interviews = SqliteInterviewStore(database)
        transcripts = SqliteTranscriptStore(database)
        await interviews.create(
            InterviewRecord(
                id=InterviewId("interview-events"),
                candidate_name="Transcript Candidate",
                state=InterviewState.CREATED,
                created_at=NOW,
            )
        )
        stage = StageRecord(
            id=StageId("stage-events"),
            interview_id=InterviewId("interview-events"),
            kind=StageKind.HR,
            state=StageState.ACTIVE,
            created_at=NOW,
        )
        await transcripts.create_stage(stage)
        session = EventSession()
        bridge = LiveKitTranscriptBridge(clock=FakeClock(NOW), transcripts=transcripts)
        bridge.attach(cast(AgentSession[object], session), stage.id)

        session.emit(
            "user_input_transcribed",
            UserInputTranscribedEvent(transcript="partial", is_final=False, item_id="candidate-1"),
        )
        session.emit(
            "user_input_transcribed",
            UserInputTranscribedEvent(
                transcript="  I documented the trade-offs.  ",
                is_final=True,
                item_id="candidate-1",
            ),
        )
        session.emit(
            "conversation_item_added",
            ConversationItemAddedEvent(
                item=ChatMessage(
                    id="interviewer-1",
                    role="assistant",
                    content=["What was the outcome?"],
                )
            ),
        )
        session.emit(
            "conversation_item_added",
            ConversationItemAddedEvent(
                item=ChatMessage(id="ignored-user", role="user", content=["duplicate path"])
            ),
        )

        await bridge.flush_and_detach()
        turns = await transcripts.list_turns(stage.id, final_only=True)
        assert [(turn.speaker, turn.text) for turn in turns] == [
            (Speaker.CANDIDATE, "I documented the trade-offs."),
            (Speaker.INTERVIEWER, "What was the outcome?"),
        ]
        assert turns[0].delivery_status is DeliveryStatus.DELIVERED
        assert turns[1].delivery_status is DeliveryStatus.UNCERTAIN
        assert session.handlers == {}

    asyncio.run(exercise())
