import asyncio
from datetime import UTC, datetime
from pathlib import Path

from interview_app.adapters.fakes import FakeClock, FakeScoreConsumer, FakeStageRuntime
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteScoreTaskStore,
    SqliteTranscriptStore,
)
from interview_app.application.handoff import TwoStageHandoffController
from interview_app.application.ports.interview_store import InterviewStateConflictError
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
    ScoreTaskState,
    Speaker,
    StageKind,
    TurnId,
    TurnRecord,
)

NOW = datetime(2026, 9, 20, 14, 0, tzinfo=UTC)


def test_handoff_is_ordered_idempotent_and_scoring_independent(tmp_path: Path) -> None:
    async def exercise() -> None:
        clock = FakeClock(NOW)
        database = SqliteDatabase(tmp_path / "handoff.sqlite3")
        await database.migrate()
        interviews = SqliteInterviewStore(database)
        transcripts = SqliteTranscriptStore(database)
        tasks = SqliteScoreTaskStore(database)
        hr = FakeStageRuntime(clock)
        technical = FakeStageRuntime(clock)
        controller = TwoStageHandoffController(
            clock=clock,
            interviews=interviews,
            transcripts=transcripts,
            runtimes={StageKind.HR: hr, StageKind.TECHNICAL: technical},
            hr_rubric_version="hr-v1",
        )
        interview = InterviewRecord(
            id=InterviewId("interview-handoff"),
            candidate_name="Same Room Candidate",
            state=InterviewState.CREATED,
            created_at=NOW,
            room_name="interview-room",
            room_sid="RM_same",
            candidate_identity="candidate-generated-id",
        )
        hr_stage = await controller.begin(interview)
        try:
            await interviews.create(
                InterviewRecord(
                    id=InterviewId("second-active"),
                    candidate_name="Another Candidate",
                    state=InterviewState.CREATED,
                    created_at=NOW,
                )
            )
        except InterviewStateConflictError as error:
            assert "Active interview" in str(error)
        else:
            raise AssertionError("A second active interview must be rejected atomically.")
        final_answer = TurnRecord(
            id=TurnId("hr-final-answer"),
            stage_id=hr_stage.id,
            speaker=Speaker.CANDIDATE,
            text="I resolved the disagreement by documenting the trade-offs.",
            is_final=True,
            delivery_status=DeliveryStatus.DELIVERED,
            occurred_at=NOW,
        )
        await transcripts.append_turn(final_answer)

        result, duplicate = await asyncio.gather(
            controller.handoff(interview.id),
            controller.handoff(interview.id),
        )
        assert duplicate == result
        assert result.payload.turns[0].text == final_answer.text
        assert result.snapshot.turn_ids == (final_answer.id,)
        assert result.score_task.state is ScoreTaskState.PENDING
        assert hr.start_context is not None
        assert technical.start_context is not None
        assert hr.start_context.room_sid == technical.start_context.room_sid == "RM_same"
        assert (
            hr.start_context.candidate_identity
            == technical.start_context.candidate_identity
            == "candidate-generated-id"
        )
        assert technical.start_context.handoff == result.payload
        assert hr.start_context.stage.session_reference != result.technical_stage.session_reference
        assert (await interviews.get(interview.id)).state is InterviewState.TECH_ACTIVE

        release = asyncio.Event()
        consumer = FakeScoreConsumer(
            store=tasks,
            clock=clock,
            release=release,
        )
        scoring = asyncio.create_task(consumer.run_one())
        await consumer.claimed.wait()
        assert not scoring.done()
        assert technical.start_context is not None
        release.set()
        completed = await scoring
        assert completed is not None
        assert completed.state is ScoreTaskState.SUCCEEDED

    asyncio.run(exercise())
