import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from interview_app.adapters.artifacts import LocalArtifactStore
from interview_app.adapters.fakes import FakeClock
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecordingManifestStore,
    SqliteRecoveryStore,
    SqliteRetentionStore,
    SqliteScoreTaskStore,
    SqliteTranscriptStore,
)
from interview_app.application.ports.interview_store import InterviewNotFoundError
from interview_app.application.ports.score_task_store import ScoreTaskLeaseError
from interview_app.application.recovery import (
    PermanentRecoveryError,
    ReconcileInterruptedInterviews,
    ReconnectResult,
    RecoverInterview,
    TransientRecoveryError,
)
from interview_app.application.retention import CleanupExpiredInterviews
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
    RecordingId,
    RecordingManifest,
    RecordingSegment,
    RecordingSegmentId,
    RecordingStatus,
    RecoveryCheckpoint,
    Speaker,
    StageId,
    StageKind,
    StageRecord,
    StageState,
    TurnId,
    TurnRecord,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


class ScriptedReconnector:
    def __init__(self, outcomes: list[ReconnectResult | Exception]) -> None:
        self._outcomes = outcomes

    async def reconnect(self, checkpoint: RecoveryCheckpoint) -> ReconnectResult:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


async def _create_recoverable(database: SqliteDatabase) -> RecoveryCheckpoint:
    await database.migrate()
    interviews = SqliteInterviewStore(database)
    transcripts = SqliteTranscriptStore(database)
    interview_id = InterviewId("recovery-interview")
    stage_id = StageId("recovery-stage")
    question_id = TurnId("interrupted-question")
    await interviews.create(
        InterviewRecord(
            id=interview_id,
            candidate_name="Synthetic Candidate",
            state=InterviewState.HR_ACTIVE,
            created_at=NOW,
            room_name="interview-recovery",
            room_sid="RM_old",
            candidate_identity="candidate-recovery",
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=stage_id,
            interview_id=interview_id,
            kind=StageKind.HR,
            state=StageState.ACTIVE,
            created_at=NOW,
        )
    )
    await transcripts.append_turn(
        TurnRecord(
            id=question_id,
            stage_id=stage_id,
            speaker=Speaker.INTERVIEWER,
            text="Tell me about a time you resolved a disagreement.",
            is_final=True,
            delivery_status=DeliveryStatus.UNCERTAIN,
            occurred_at=NOW,
        )
    )
    return RecoveryCheckpoint(
        interview_id=interview_id,
        stage_id=stage_id,
        stage_kind=StageKind.HR,
        resumable_state=InterviewState.HR_ACTIVE,
        remaining_active_seconds=217.5,
        last_committed_turn_id=question_id,
        last_committed_event_id=None,
        interrupted_question_turn_id=question_id,
        room_name="interview-recovery",
        room_sid="RM_old",
        candidate_identity="candidate-recovery",
        active_recording_segment_id=None,
        recovery_started_at=None,
        recovery_deadline_at=None,
        recovery_attempts=0,
        updated_at=NOW,
    )


def test_recovery_resumes_same_stage_and_remaining_time_after_transient_failures(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "recovery.sqlite3")
        checkpoint = await _create_recoverable(database)
        store = SqliteRecoveryStore(database)
        clock = FakeClock(now=NOW)

        async def advance(seconds: float) -> None:
            clock.advance(seconds)

        recovery = RecoverInterview(
            store=store,
            clock=clock,
            reconnector=ScriptedReconnector(
                [
                    TransientRecoveryError("room temporarily unavailable"),
                    TransientRecoveryError("participant not rebound yet"),
                    ReconnectResult(room_sid="RM_new"),
                ]
            ),
            sleep=advance,
        )

        outcome = await recovery.execute(checkpoint)

        assert outcome.resumed
        assert outcome.checkpoint.stage_id == checkpoint.stage_id
        assert outcome.checkpoint.remaining_active_seconds == 217.5
        assert outcome.checkpoint.room_sid == "RM_new"
        assert outcome.checkpoint.recovery_attempts == 3
        assert outcome.reask_question_turn_id == TurnId("interrupted-question")
        stored = await SqliteInterviewStore(database).get(checkpoint.interview_id)
        assert stored.state is InterviewState.HR_ACTIVE
        assert stored.room_sid == "RM_new"

    asyncio.run(exercise())


def test_recovery_timeout_and_startup_reconciliation_preserve_partial_state(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "timeout.sqlite3")
        checkpoint = await _create_recoverable(database)
        store = SqliteRecoveryStore(database)
        clock = FakeClock(now=NOW)

        class AlwaysUnavailable:
            async def reconnect(self, checkpoint: RecoveryCheckpoint) -> ReconnectResult:
                raise TransientRecoveryError("local server unavailable")

        async def advance(seconds: float) -> None:
            clock.advance(seconds)

        outcome = await RecoverInterview(
            store=store,
            clock=clock,
            reconnector=AlwaysUnavailable(),
            sleep=advance,
        ).execute(checkpoint)
        assert not outcome.resumed
        assert outcome.incomplete_reason == "Recovery deadline exhausted."
        assert outcome.checkpoint.remaining_active_seconds == 217.5
        interview = await SqliteInterviewStore(database).get(checkpoint.interview_id)
        assert interview.state is InterviewState.INCOMPLETE

        second_database = SqliteDatabase(tmp_path / "reconcile.sqlite3")
        second_checkpoint = await _create_recoverable(second_database)
        second_store = SqliteRecoveryStore(second_database)
        expired_recovery = replace(
            second_checkpoint,
            recovery_started_at=NOW - timedelta(minutes=3),
            recovery_deadline_at=NOW - timedelta(minutes=1),
        )
        await second_store.enter_recovery(
            expired_recovery,
            expected=InterviewState.HR_ACTIVE,
        )
        reconciled = await ReconcileInterruptedInterviews(
            store=second_store,
            clock=FakeClock(now=NOW),
        ).execute()
        assert reconciled.resumable == ()
        assert reconciled.marked_incomplete == (second_checkpoint.interview_id,)
        assert (
            await SqliteInterviewStore(second_database).get(second_checkpoint.interview_id)
        ).state is InterviewState.INCOMPLETE

    asyncio.run(exercise())


def test_permanent_recovery_failure_does_not_consume_retry_budget(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "permanent.sqlite3")
        checkpoint = await _create_recoverable(database)
        clock = FakeClock(now=NOW)
        sleeps: list[float] = []

        class InvalidCredentials:
            async def reconnect(self, checkpoint: RecoveryCheckpoint) -> ReconnectResult:
                raise PermanentRecoveryError("invalid local server credentials")

        async def record_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        outcome = await RecoverInterview(
            store=SqliteRecoveryStore(database),
            clock=clock,
            reconnector=InvalidCredentials(),
            sleep=record_sleep,
        ).execute(checkpoint)

        assert not outcome.resumed
        assert outcome.incomplete_reason is not None
        assert outcome.incomplete_reason.startswith("Permanent recovery failure:")
        assert sleeps == []
        assert clock.utc_now() == NOW

    asyncio.run(exercise())


def test_restart_continues_the_persisted_recovery_incident(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "restart-recovery.sqlite3")
        checkpoint = await _create_recoverable(database)
        store = SqliteRecoveryStore(database)
        persisted = replace(
            checkpoint,
            recovery_started_at=NOW - timedelta(seconds=60),
            recovery_deadline_at=NOW + timedelta(seconds=60),
            recovery_attempts=2,
        )
        await store.enter_recovery(persisted, expected=InterviewState.HR_ACTIVE)
        reconciled = await ReconcileInterruptedInterviews(
            store=store,
            clock=FakeClock(now=NOW),
        ).execute()
        assert reconciled.resumable == (persisted,)

        async def unexpected_sleep(seconds: float) -> None:
            raise AssertionError(f"Successful restart recovery tried to sleep {seconds} seconds")

        outcome = await RecoverInterview(
            store=store,
            clock=FakeClock(now=NOW),
            reconnector=ScriptedReconnector([ReconnectResult(room_sid="RM_after_restart")]),
            sleep=unexpected_sleep,
        ).execute(reconciled.resumable[0])
        assert outcome.resumed
        assert outcome.checkpoint.recovery_attempts == 3
        assert outcome.checkpoint.room_sid == "RM_after_restart"

    asyncio.run(exercise())


async def _create_retention_fixture(
    database: SqliteDatabase,
    data_root: Path,
) -> tuple[InterviewId, InterviewId, object]:
    await database.migrate()
    interviews = SqliteInterviewStore(database)
    transcripts = SqliteTranscriptStore(database)
    expired_id = InterviewId("expired-interview")
    recent_id = InterviewId("recent-interview")
    started_at = NOW - timedelta(days=30)
    await interviews.create(
        InterviewRecord(
            id=expired_id,
            candidate_name="Expired Candidate",
            state=InterviewState.INTERVIEW_FINISHED,
            created_at=started_at,
        )
    )
    await interviews.create(
        InterviewRecord(
            id=recent_id,
            candidate_name="Recent Candidate",
            state=InterviewState.INTERVIEW_FINISHED,
            created_at=NOW - timedelta(days=29),
        )
    )
    stage_id = StageId("expired-stage")
    await transcripts.create_stage(
        StageRecord(
            id=stage_id,
            interview_id=expired_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=started_at,
        )
    )
    await transcripts.append_turn(
        TurnRecord(
            id=TurnId("expired-answer"),
            stage_id=stage_id,
            speaker=Speaker.CANDIDATE,
            text="Candidate evidence that must expire.",
            is_final=True,
            delivery_status=DeliveryStatus.DELIVERED,
            occurred_at=started_at,
        )
    )
    _, task = await transcripts.finalize_snapshot_and_enqueue(
        stage_id,
        rubric_version="hr-v1",
        created_at=started_at,
    )
    recording_id = RecordingId("expired-recording")
    segment_id = RecordingSegmentId("expired-segment")
    relative_path = f"{recording_id}/{segment_id}.wav"
    directory = data_root / str(recording_id)
    directory.mkdir(parents=True)
    (directory / f"{segment_id}.wav").write_bytes(b"RIFF synthetic")
    (directory / "manifest.json").write_text("{}", encoding="utf-8")
    await SqliteRecordingManifestStore(database).save(
        RecordingManifest(
            id=recording_id,
            interview_id=expired_id,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            started_at=started_at,
            completed_at=started_at + timedelta(minutes=5),
            status=RecordingStatus.COMPLETE,
            failure=None,
            segments=(
                RecordingSegment(
                    id=segment_id,
                    recording_id=recording_id,
                    stage_id=stage_id,
                    speaker=Speaker.CANDIDATE,
                    relative_path=relative_path,
                    offset_seconds=0,
                    duration_seconds=1,
                    checksum_sha256="synthetic",
                    status=RecordingStatus.COMPLETE,
                    gaps=(),
                ),
            ),
        )
    )
    return expired_id, recent_id, task


def test_cleanup_exact_boundary_removes_files_rows_and_blocks_late_worker(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "retention.sqlite3")
        data_root = tmp_path / "recordings"
        expired_id, recent_id, task = await _create_retention_fixture(database, data_root)
        tasks = SqliteScoreTaskStore(database)
        claimed = await tasks.claim_next(
            worker_id="slow-worker",
            now=NOW - timedelta(days=1),
            lease_duration=timedelta(days=2),
        )
        assert claimed is not None and claimed.id == task.id

        report = await CleanupExpiredInterviews(
            store=SqliteRetentionStore(database),
            artifacts=LocalArtifactStore(data_root),
            clock=FakeClock(now=NOW),
        ).execute()

        assert report.deleted == (expired_id,)
        assert report.failed == ()
        assert not (data_root / "expired-recording").exists()
        assert (await SqliteInterviewStore(database).get(recent_id)).id == recent_id
        try:
            await SqliteInterviewStore(database).get(expired_id)
        except InterviewNotFoundError:
            pass
        else:
            raise AssertionError("Expired interview rows must be removed.")
        try:
            await tasks.complete(
                task.id,
                worker_id="slow-worker",
                completed_at=NOW,
            )
        except ScoreTaskLeaseError:
            pass
        else:
            raise AssertionError("A late worker must not recreate expired results.")

        async def count_candidate_rows(connection: aiosqlite.Connection) -> int:
            total = 0
            for table in ("stages", "turns", "snapshots", "score_tasks", "recordings"):
                cursor = await connection.execute(f"SELECT COUNT(*) FROM {table}")
                row = await cursor.fetchone()
                total += int(row[0])
            return total

        assert await database.read(count_candidate_rows) == 0

    asyncio.run(exercise())


def test_cleanup_file_failure_is_visible_retryable_and_symlinks_are_rejected(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "retry.sqlite3")
        await database.migrate()
        interview_id = InterviewId("retry-expired")
        await SqliteInterviewStore(database).create(
            InterviewRecord(
                id=interview_id,
                candidate_name="Retry Candidate",
                state=InterviewState.INTERVIEW_FINISHED,
                created_at=NOW - timedelta(days=31),
            )
        )

        class FailOnceArtifacts:
            def __init__(self) -> None:
                self.calls = 0

            async def delete(self, relative_paths: tuple[str, ...]) -> tuple[str, ...]:
                self.calls += 1
                return ("synthetic/failure",) if self.calls == 1 else ()

        artifacts = FailOnceArtifacts()
        cleanup = CleanupExpiredInterviews(
            store=SqliteRetentionStore(database),
            artifacts=artifacts,
            clock=FakeClock(now=NOW),
        )
        first = await cleanup.execute()
        assert first.failed == (interview_id,)

        async def interview_row_exists(connection: aiosqlite.Connection) -> bool:
            cursor = await connection.execute(
                "SELECT 1 FROM interviews WHERE id = ?",
                (interview_id,),
            )
            return await cursor.fetchone() is not None

        assert await database.read(interview_row_exists)
        pending = await SqliteRetentionStore(database).list_pending()
        assert pending[0].failed_paths == ("synthetic/failure",)
        second = await cleanup.execute()
        assert second.deleted == (interview_id,)

        data_root = tmp_path / "owned"
        outside = tmp_path / "outside.txt"
        data_root.mkdir()
        outside.write_text("must remain", encoding="utf-8")
        (data_root / "link").symlink_to(outside)
        failures = await LocalArtifactStore(data_root).delete(("link", "../outside.txt"))
        assert failures == ("link", "../outside.txt")
        assert outside.read_text(encoding="utf-8") == "must remain"

    asyncio.run(exercise())
