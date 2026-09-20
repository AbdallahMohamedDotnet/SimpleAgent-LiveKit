import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteScoreTaskStore,
    SqliteTranscriptStore,
)
from interview_app.application.ports.score_task_store import ScoreTaskLeaseError
from interview_app.application.ports.transcript_store import EvidenceConflictError
from interview_app.domain.models import (
    DeliveryStatus,
    EventId,
    InterviewId,
    InterviewRecord,
    InterviewState,
    ScoreTaskState,
    Speaker,
    StageEvent,
    StageEventType,
    StageId,
    StageKind,
    StageRecord,
    StageState,
    TurnId,
    TurnRecord,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _interview(identifier: str = "interview-1") -> InterviewRecord:
    return InterviewRecord(
        id=InterviewId(identifier),
        candidate_name="Repeatable Candidate Name",
        state=InterviewState.CREATED,
        created_at=NOW,
    )


def _stage(identifier: str = "stage-1") -> StageRecord:
    return StageRecord(
        id=StageId(identifier),
        interview_id=InterviewId("interview-1"),
        kind=StageKind.HR,
        state=StageState.ACTIVE,
        created_at=NOW,
    )


def _turn(
    identifier: str,
    *,
    text: str,
    final: bool = True,
    offset_seconds: int = 0,
) -> TurnRecord:
    return TurnRecord(
        id=TurnId(identifier),
        stage_id=StageId("stage-1"),
        speaker=Speaker.CANDIDATE,
        text=text,
        is_final=final,
        delivery_status=DeliveryStatus.DELIVERED,
        occurred_at=NOW + timedelta(seconds=offset_seconds),
    )


def test_restart_preserves_turns_snapshot_and_leased_task(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "interviews.sqlite3"
        database = SqliteDatabase(path)
        await database.migrate()
        await database.migrate()
        interviews = SqliteInterviewStore(database)
        transcripts = SqliteTranscriptStore(database)
        await interviews.create(_interview())
        await transcripts.create_stage(_stage())

        interim = _turn("turn-interim", text="partial", final=False)
        final = _turn("turn-final", text="complete answer", offset_seconds=1)
        assert await transcripts.append_turn(interim)
        assert await transcripts.append_turn(final)
        assert not await transcripts.append_turn(final)

        snapshot, task = await transcripts.finalize_snapshot_and_enqueue(
            StageId("stage-1"), rubric_version="hr-v1", created_at=NOW + timedelta(seconds=2)
        )
        assert snapshot.turn_ids == (TurnId("turn-final"),)
        assert task.state is ScoreTaskState.PENDING

        restarted_database = SqliteDatabase(path)
        await restarted_database.migrate()
        restarted_transcripts = SqliteTranscriptStore(restarted_database)
        restarted_tasks = SqliteScoreTaskStore(restarted_database)
        assert await restarted_transcripts.list_turns(StageId("stage-1"), final_only=False) == (
            interim,
            final,
        )
        (
            duplicate_snapshot,
            duplicate_task,
        ) = await restarted_transcripts.finalize_snapshot_and_enqueue(
            StageId("stage-1"),
            rubric_version="hr-v1",
            created_at=NOW + timedelta(seconds=10),
        )
        assert duplicate_snapshot.id == snapshot.id
        assert duplicate_task.id == task.id

        first_claim = await restarted_tasks.claim_next(
            worker_id="worker-1",
            now=NOW + timedelta(seconds=3),
            lease_duration=timedelta(seconds=30),
        )
        assert first_claim is not None
        assert first_claim.id == task.id
        assert first_claim.attempts == 1
        assert (
            await restarted_tasks.claim_next(
                worker_id="worker-2",
                now=NOW + timedelta(seconds=4),
                lease_duration=timedelta(seconds=30),
            )
            is None
        )

        second_claim = await restarted_tasks.claim_next(
            worker_id="worker-2",
            now=NOW + timedelta(seconds=34),
            lease_duration=timedelta(seconds=30),
        )
        assert second_claim is not None
        assert second_claim.id == task.id
        assert second_claim.attempts == 2
        try:
            await restarted_tasks.complete(
                task.id, worker_id="worker-1", completed_at=NOW + timedelta(seconds=35)
            )
        except ScoreTaskLeaseError:
            pass
        else:
            raise AssertionError("A stale lease owner must not complete a reclaimed task.")

        completed = await restarted_tasks.complete(
            task.id, worker_id="worker-2", completed_at=NOW + timedelta(seconds=35)
        )
        assert completed.state is ScoreTaskState.SUCCEEDED
        assert (
            await restarted_tasks.complete(
                task.id, worker_id="worker-2", completed_at=NOW + timedelta(seconds=36)
            )
        ) == completed

        try:
            await restarted_transcripts.append_turn(
                _turn("too-late", text="must not mutate frozen evidence", offset_seconds=40)
            )
        except EvidenceConflictError as error:
            assert "frozen" in str(error)
        else:
            raise AssertionError("Expected frozen stage evidence to reject later turns.")

    asyncio.run(exercise())


def test_duplicate_conflicts_and_concurrent_short_writes(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "concurrent.sqlite3", busy_timeout_ms=2_000)
        await database.migrate()
        interviews = SqliteInterviewStore(database)
        transcripts = SqliteTranscriptStore(database)
        await interviews.create(_interview())
        await interviews.create(
            replace(_interview("interview-2"), state=InterviewState.INTERVIEW_FINISHED)
        )
        await transcripts.create_stage(_stage())
        await transcripts.create_stage(_stage())

        try:
            await transcripts.create_stage(replace(_stage(), state=StageState.CLOSED))
        except EvidenceConflictError as error:
            assert "Stage ID conflict" in str(error)
        else:
            raise AssertionError("Reused stage IDs with changed evidence must fail.")

        started_event = StageEvent(
            id=EventId("stage-started-event"),
            interview_id=InterviewId("interview-1"),
            stage_id=StageId("stage-1"),
            stage_kind=StageKind.HR,
            type=StageEventType.STARTED,
            occurred_at=NOW,
        )
        assert await transcripts.append_event(started_event)
        assert not await transcripts.append_event(started_event)
        try:
            await transcripts.append_event(
                StageEvent(
                    id=started_event.id,
                    interview_id=started_event.interview_id,
                    stage_id=started_event.stage_id,
                    stage_kind=started_event.stage_kind,
                    type=StageEventType.CLOSED,
                    occurred_at=started_event.occurred_at,
                )
            )
        except EvidenceConflictError as error:
            assert "Event ID conflict" in str(error)
        else:
            raise AssertionError("Reused event IDs with changed evidence must fail.")

        original = _turn("same-event", text="original")
        assert await transcripts.append_turn(original)
        try:
            await transcripts.append_turn(_turn("same-event", text="changed"))
        except EvidenceConflictError as error:
            assert "Turn ID conflict" in str(error)
        else:
            raise AssertionError("Reused turn IDs with changed evidence must fail.")

        turns = [
            _turn(f"concurrent-{index}", text=f"answer {index}", offset_seconds=index + 1)
            for index in range(20)
        ]
        inserted = await asyncio.gather(*(transcripts.append_turn(turn) for turn in turns))
        assert all(inserted)
        assert len(await transcripts.list_turns(StageId("stage-1"), final_only=True)) == 21

        async def pragma(connection: aiosqlite.Connection, name: str) -> object:
            cursor = await connection.execute(f"PRAGMA {name}")
            row = await cursor.fetchone()
            return row[0]

        journal_mode = str(
            await database.read(lambda connection: pragma(connection, "journal_mode"))
        )
        foreign_keys = int(
            await database.read(lambda connection: pragma(connection, "foreign_keys"))
        )
        assert journal_mode == "wal"
        assert foreign_keys == 1

        async def migration_count(connection: aiosqlite.Connection) -> int:
            cursor = await connection.execute("SELECT COUNT(*) FROM schema_migrations")
            row = await cursor.fetchone()
            return int(row[0])

        assert await database.read(migration_count) == 4

    asyncio.run(exercise())
