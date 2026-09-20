"""Translate LiveKit session events into durable transcript evidence."""

import asyncio
from uuid import uuid4

from livekit.agents import AgentSession
from livekit.agents.llm import ChatMessage
from livekit.agents.voice.events import ConversationItemAddedEvent, UserInputTranscribedEvent

from interview_app.application.ports.clock import Clock
from interview_app.application.ports.transcript_store import TranscriptStore
from interview_app.domain.models import DeliveryStatus, Speaker, StageId, TurnId, TurnRecord


class LiveKitTranscriptBridge:
    """Own and flush persistence tasks created by synchronous SDK callbacks."""

    def __init__(self, *, clock: Clock, transcripts: TranscriptStore) -> None:
        self._clock = clock
        self._transcripts = transcripts
        self._stage_id: StageId | None = None
        self._session: AgentSession[object] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def attach(self, session: AgentSession[object], stage_id: StageId) -> None:
        if self._session is not None:
            raise RuntimeError("The transcript bridge is already attached to a session.")
        self._session = session
        self._stage_id = stage_id
        session.on("user_input_transcribed", self._on_user_input_transcribed)
        session.on("conversation_item_added", self._on_conversation_item_added)

    async def flush_and_detach(self) -> None:
        session = self._session
        if session is None:
            return
        session.off("user_input_transcribed", self._on_user_input_transcribed)
        session.off("conversation_item_added", self._on_conversation_item_added)
        self._session = None

        tasks = tuple(self._tasks)
        self._tasks.clear()
        if tasks:
            await asyncio.gather(*tasks)
        self._stage_id = None

    def _on_user_input_transcribed(self, event: UserInputTranscribedEvent) -> None:
        if not event.is_final or not event.transcript.strip():
            return
        self._schedule(
            TurnRecord(
                id=TurnId(event.item_id or str(uuid4())),
                stage_id=self._require_stage_id(),
                speaker=Speaker.CANDIDATE,
                text=event.transcript.strip(),
                is_final=True,
                delivery_status=DeliveryStatus.DELIVERED,
                occurred_at=self._clock.utc_now(),
            )
        )

    def _on_conversation_item_added(self, event: ConversationItemAddedEvent) -> None:
        item = event.item
        if not isinstance(item, ChatMessage) or item.role != "assistant":
            return
        text = item.text_content
        if not text or not text.strip():
            return
        self._schedule(
            TurnRecord(
                id=TurnId(item.id),
                stage_id=self._require_stage_id(),
                speaker=Speaker.INTERVIEWER,
                text=text.strip(),
                is_final=True,
                # Generated text does not prove that its audio reached the candidate.
                delivery_status=DeliveryStatus.UNCERTAIN,
                occurred_at=self._clock.utc_now(),
            )
        )

    def _schedule(self, record: TurnRecord) -> None:
        self._tasks.add(asyncio.create_task(self._persist(record)))

    async def _persist(self, record: TurnRecord) -> None:
        await self._transcripts.append_turn(record)

    def _require_stage_id(self) -> StageId:
        if self._stage_id is None:
            raise RuntimeError("The transcript bridge is not attached to a stage.")
        return self._stage_id
