"""SQLite implementations of interview, transcript, and score-task ports."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import aiosqlite

from interview_app.adapters.sqlite.database import SqliteDatabase
from interview_app.application.ports.interview_store import (
    InterviewNotFoundError,
    InterviewStateConflictError,
)
from interview_app.application.ports.recording import RecordingLifecycleError
from interview_app.application.ports.recovery_store import RecoveryStateError
from interview_app.application.ports.score_task_store import ScoreTaskLeaseError
from interview_app.application.ports.transcript_store import EvidenceConflictError
from interview_app.domain.models import (
    ConnectionAttempt,
    DeletionJob,
    DeletionJobState,
    DeliveryStatus,
    EventId,
    InterruptedInterview,
    InterviewId,
    InterviewRecord,
    InterviewState,
    RecordingGap,
    RecordingId,
    RecordingManifest,
    RecordingSegment,
    RecordingSegmentId,
    RecordingStatus,
    RecoveryCheckpoint,
    ScoreTaskId,
    ScoreTaskRecord,
    ScoreTaskState,
    SnapshotId,
    Speaker,
    StageEvent,
    StageId,
    StageKind,
    StageRecord,
    StageState,
    TranscriptSnapshot,
    TurnId,
    TurnRecord,
)
from interview_app.domain.policies import RetentionPolicy
from interview_app.domain.scoring import (
    AssessmentStatus,
    AssessmentTaskInput,
    CompetencyAssessment,
    EvidenceCitation,
    StageAssessment,
    StageScoreRecord,
)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Persisted timestamps must be timezone-aware.")
    return value.astimezone(UTC).isoformat()


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


_RETENTION_POLICY = RetentionPolicy()


class SqliteInterviewStore:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def create(self, record: InterviewRecord) -> None:
        async def operation(connection: aiosqlite.Connection) -> None:
            if record.state not in {
                InterviewState.INTERVIEW_FINISHED,
                InterviewState.INCOMPLETE,
            }:
                active = await _fetchone(
                    connection,
                    """
                    SELECT id FROM interviews
                    WHERE state NOT IN (?, ?)
                    LIMIT 1
                    """,
                    (
                        InterviewState.INTERVIEW_FINISHED.value,
                        InterviewState.INCOMPLETE.value,
                    ),
                )
                if active is not None:
                    raise InterviewStateConflictError(
                        f"Active interview already exists: {active['id']}"
                    )
            try:
                await connection.execute(
                    """
                    INSERT INTO interviews(
                        id, candidate_name, state, created_at,
                        room_name, room_sid, candidate_identity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.candidate_name,
                        record.state.value,
                        _utc_text(record.created_at),
                        record.room_name,
                        record.room_sid,
                        record.candidate_identity,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise InterviewStateConflictError(
                    f"Interview cannot be created: {record.id}"
                ) from error

        await self._database.write(operation)

    async def get(
        self,
        interview_id: InterviewId,
        *,
        now: datetime | None = None,
    ) -> InterviewRecord:
        async def operation(connection: aiosqlite.Connection) -> InterviewRecord:
            cutoff = _utc_text(_RETENTION_POLICY.expired_start_cutoff(now=now or datetime.now(UTC)))
            row = await _fetchone(
                connection,
                """
                SELECT interview.* FROM interviews AS interview
                WHERE interview.id = ? AND interview.created_at > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM deletion_jobs AS deletion
                      WHERE deletion.interview_id = interview.id
                  )
                """,
                (interview_id, cutoff),
            )
            if row is None:
                raise InterviewNotFoundError(f"Unknown or expired interview: {interview_id}")
            return _interview(row)

        return await self._database.read(operation)

    async def transition(
        self,
        interview_id: InterviewId,
        *,
        expected: InterviewState,
        target: InterviewState,
    ) -> InterviewRecord:
        async def operation(connection: aiosqlite.Connection) -> InterviewRecord:
            cutoff = _utc_text(_RETENTION_POLICY.expired_start_cutoff(now=datetime.now(UTC)))
            cursor = await connection.execute(
                """
                UPDATE interviews SET state = ?
                WHERE id = ? AND state = ? AND created_at > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM deletion_jobs WHERE deletion_jobs.interview_id = interviews.id
                  )
                """,
                (target.value, interview_id, expected.value, cutoff),
            )
            if cursor.rowcount != 1:
                row = await _fetchone(
                    connection, "SELECT state FROM interviews WHERE id = ?", (interview_id,)
                )
                if row is None:
                    raise InterviewNotFoundError(f"Unknown interview: {interview_id}")
                raise InterviewStateConflictError(
                    f"Expected {expected.value}, found {row['state']}."
                )
            row = await _fetchone(
                connection,
                "SELECT * FROM interviews WHERE id = ?",
                (interview_id,),
            )
            if row is None:
                raise InterviewNotFoundError(f"Unknown interview: {interview_id}")
            return _interview(row)

        return await self._database.write(operation)


class SqliteTranscriptStore:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def create_stage(self, stage: StageRecord) -> None:
        async def operation(connection: aiosqlite.Connection) -> None:
            values = (
                stage.id,
                stage.interview_id,
                stage.kind.value,
                stage.state.value,
                _utc_text(stage.created_at),
                stage.session_reference,
            )
            try:
                await connection.execute(
                    """
                    INSERT INTO stages(
                        id, interview_id, kind, state, created_at, session_reference
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
            except sqlite3.IntegrityError as error:
                row = await _fetchone(
                    connection,
                    """
                    SELECT id, interview_id, kind, state, created_at, session_reference
                    FROM stages WHERE id = ?
                    """,
                    (stage.id,),
                )
                if row is not None and tuple(row) == values:
                    return
                raise EvidenceConflictError(f"Stage ID conflict: {stage.id}") from error

        await self._database.write(operation)

    async def transition_stage(
        self,
        stage_id: StageId,
        *,
        expected: StageState,
        target: StageState,
    ) -> StageRecord:
        async def operation(connection: aiosqlite.Connection) -> StageRecord:
            await _ensure_stage_is_retained(connection, stage_id, datetime.now(UTC))
            cursor = await connection.execute(
                "UPDATE stages SET state = ? WHERE id = ? AND state = ?",
                (target.value, stage_id, expected.value),
            )
            if cursor.rowcount != 1:
                row = await _fetchone(
                    connection, "SELECT state FROM stages WHERE id = ?", (stage_id,)
                )
                if row is None:
                    raise EvidenceConflictError(f"Unknown stage: {stage_id}")
                raise EvidenceConflictError(
                    f"Expected stage state {expected.value}, found {row['state']}."
                )
            row = await _fetchone(connection, "SELECT * FROM stages WHERE id = ?", (stage_id,))
            if row is None:
                raise RuntimeError("Transitioned stage disappeared.")
            return _stage(row)

        return await self._database.write(operation)

    async def append_event(self, event: StageEvent) -> bool:
        values = (
            event.id,
            event.interview_id,
            event.stage_id,
            event.stage_kind.value,
            event.type.value,
            _utc_text(event.occurred_at),
        )

        async def operation(connection: aiosqlite.Connection) -> bool:
            await _ensure_stage_is_retained(connection, event.stage_id, event.occurred_at)
            try:
                await connection.execute(
                    """
                    INSERT INTO events(id, interview_id, stage_id, stage_kind, type, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                return True
            except sqlite3.IntegrityError as error:
                row = await _fetchone(connection, "SELECT * FROM events WHERE id = ?", (event.id,))
                if row is not None and tuple(row) == values:
                    return False
                raise EvidenceConflictError(f"Event ID conflict: {event.id}") from error

        return await self._database.write(operation)

    async def append_turn(self, turn: TurnRecord) -> bool:
        async def operation(connection: aiosqlite.Connection) -> bool:
            await _ensure_stage_is_retained(connection, turn.stage_id, turn.occurred_at)
            frozen = await _fetchone(
                connection,
                "SELECT 1 FROM snapshots WHERE stage_id = ? LIMIT 1",
                (turn.stage_id,),
            )
            if frozen is not None:
                raise EvidenceConflictError(
                    "Cannot append evidence after a stage snapshot is frozen."
                )
            values = _turn_values(turn)
            try:
                await connection.execute(
                    """
                    INSERT INTO turns(
                        id, stage_id, speaker, text, is_final, delivery_status, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                return True
            except sqlite3.IntegrityError as error:
                row = await _fetchone(
                    connection,
                    """
                    SELECT id, stage_id, speaker, text, is_final, delivery_status, occurred_at
                    FROM turns WHERE id = ?
                    """,
                    (turn.id,),
                )
                if row is not None and tuple(row) == values:
                    return False
                raise EvidenceConflictError(f"Turn ID conflict: {turn.id}") from error

        return await self._database.write(operation)

    async def list_turns(self, stage_id: StageId, *, final_only: bool) -> tuple[TurnRecord, ...]:
        async def operation(connection: aiosqlite.Connection) -> tuple[TurnRecord, ...]:
            query = """
                SELECT id, stage_id, speaker, text, is_final, delivery_status, occurred_at
                FROM turns WHERE stage_id = ?
            """
            parameters: tuple[object, ...] = (stage_id,)
            if final_only:
                query += " AND is_final = ?"
                parameters += (1,)
            query += " ORDER BY occurred_at, id"
            return tuple(_turn(row) for row in await _fetchall(connection, query, parameters))

        return await self._database.read(operation)

    async def finalize_snapshot_and_enqueue(
        self,
        stage_id: StageId,
        *,
        rubric_version: str,
        created_at: datetime,
    ) -> tuple[TranscriptSnapshot, ScoreTaskRecord]:
        normalized_rubric = rubric_version.strip()
        if not normalized_rubric:
            raise ValueError("rubric_version must not be blank.")
        created_text = _utc_text(created_at)

        async def operation(
            connection: aiosqlite.Connection,
        ) -> tuple[TranscriptSnapshot, ScoreTaskRecord]:
            await _ensure_stage_is_retained(connection, stage_id, created_at)
            stage = await _fetchone(connection, "SELECT id FROM stages WHERE id = ?", (stage_id,))
            if stage is None:
                raise EvidenceConflictError(f"Unknown stage: {stage_id}")
            rows = await _fetchall(
                connection,
                """
                SELECT id, stage_id, speaker, text, is_final, delivery_status, occurred_at
                FROM turns WHERE stage_id = ? AND is_final = 1 ORDER BY occurred_at, id
                """,
                (stage_id,),
            )
            payload = [
                {
                    "delivery_status": row["delivery_status"],
                    "occurred_at": row["occurred_at"],
                    "speaker": row["speaker"],
                    "text": row["text"],
                    "turn_id": row["id"],
                }
                for row in rows
            ]
            content_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            content_hash = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
            existing = await _fetchone(
                connection,
                """
                SELECT id, stage_id, rubric_version, content_hash, content_json, created_at
                FROM snapshots WHERE stage_id = ? AND rubric_version = ?
                """,
                (stage_id, normalized_rubric),
            )
            if existing is not None:
                if existing["content_hash"] != content_hash:
                    raise EvidenceConflictError(
                        "Final evidence changed after the stage snapshot was frozen."
                    )
                task_row = await _fetchone(
                    connection,
                    "SELECT * FROM score_tasks WHERE snapshot_id = ? AND rubric_version = ?",
                    (existing["id"], normalized_rubric),
                )
                if task_row is None:
                    raise EvidenceConflictError("Snapshot exists without its atomic score task.")
                return _snapshot(existing), _score_task(task_row)

            snapshot_id = SnapshotId(str(uuid4()))
            task_id = ScoreTaskId(str(uuid4()))
            await connection.execute(
                """
                INSERT INTO snapshots(
                    id, stage_id, rubric_version, content_hash, content_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    stage_id,
                    normalized_rubric,
                    content_hash,
                    content_json,
                    created_text,
                ),
            )
            await connection.execute(
                """
                INSERT INTO score_tasks(
                    id, snapshot_id, rubric_version, state, attempts,
                    lease_owner, lease_expires_at, available_at, failure, created_at, completed_at
                ) VALUES (?, ?, ?, ?, 0, NULL, NULL, ?, NULL, ?, NULL)
                """,
                (
                    task_id,
                    snapshot_id,
                    normalized_rubric,
                    ScoreTaskState.PENDING.value,
                    created_text,
                    created_text,
                ),
            )
            snapshot_row = await _fetchone(
                connection, "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
            )
            task_row = await _fetchone(
                connection, "SELECT * FROM score_tasks WHERE id = ?", (task_id,)
            )
            if snapshot_row is None or task_row is None:
                raise RuntimeError("Atomic snapshot/task insert did not return its records.")
            return _snapshot(snapshot_row), _score_task(task_row)

        return await self._database.write(operation)


class SqliteScoreTaskStore:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> ScoreTaskRecord | None:
        normalized_worker = worker_id.strip()
        if not normalized_worker:
            raise ValueError("worker_id must not be blank.")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive.")
        now_text = _utc_text(now)
        lease_expires_text = _utc_text(now + lease_duration)

        async def operation(connection: aiosqlite.Connection) -> ScoreTaskRecord | None:
            row = await _fetchone(
                connection,
                """
                SELECT task.id
                FROM score_tasks AS task
                JOIN snapshots AS snapshot ON snapshot.id = task.snapshot_id
                JOIN stages AS stage ON stage.id = snapshot.stage_id
                JOIN interviews AS interview ON interview.id = stage.interview_id
                WHERE
                    interview.created_at > ?
                    AND NOT EXISTS (
                        SELECT 1 FROM deletion_jobs AS deletion
                        WHERE deletion.interview_id = interview.id
                    )
                    AND (
                        (task.state IN (?, ?) AND task.available_at <= ?)
                        OR (task.state = ? AND task.lease_expires_at <= ?)
                    )
                ORDER BY task.created_at, task.id
                LIMIT 1
                """,
                (
                    _utc_text(_RETENTION_POLICY.expired_start_cutoff(now=now)),
                    ScoreTaskState.PENDING.value,
                    ScoreTaskState.FAILED_RETRYABLE.value,
                    now_text,
                    ScoreTaskState.RUNNING.value,
                    now_text,
                ),
            )
            if row is None:
                return None
            await connection.execute(
                """
                UPDATE score_tasks
                SET state = ?, attempts = attempts + 1, lease_owner = ?, lease_expires_at = ?
                WHERE id = ?
                """,
                (
                    ScoreTaskState.RUNNING.value,
                    normalized_worker,
                    lease_expires_text,
                    row["id"],
                ),
            )
            claimed = await _fetchone(
                connection, "SELECT * FROM score_tasks WHERE id = ?", (row["id"],)
            )
            if claimed is None:
                raise RuntimeError("Claimed score task disappeared.")
            return _score_task(claimed)

        return await self._database.write(operation)

    async def load_input(self, task_id: ScoreTaskId) -> AssessmentTaskInput:
        async def operation(connection: aiosqlite.Connection) -> AssessmentTaskInput:
            await _ensure_task_is_retained(connection, task_id, datetime.now(UTC))
            row = await _fetchone(
                connection,
                """
                SELECT
                    t.id AS task_id, t.snapshot_id, t.rubric_version,
                    s.stage_id, st.kind AS stage_kind
                FROM score_tasks AS t
                JOIN snapshots AS s ON s.id = t.snapshot_id
                JOIN stages AS st ON st.id = s.stage_id
                WHERE t.id = ?
                """,
                (task_id,),
            )
            if row is None:
                raise ScoreTaskLeaseError(f"Unknown score task: {task_id}")
            turn_rows = await _fetchall(
                connection,
                """
                SELECT tr.id, tr.stage_id, tr.speaker, tr.text, tr.is_final,
                       tr.delivery_status, tr.occurred_at
                FROM turns AS tr
                JOIN snapshots AS s ON s.stage_id = tr.stage_id
                WHERE s.id = ? AND tr.is_final = 1
                ORDER BY tr.occurred_at, tr.id
                """,
                (row["snapshot_id"],),
            )
            return AssessmentTaskInput(
                task_id=ScoreTaskId(row["task_id"]),
                snapshot_id=SnapshotId(row["snapshot_id"]),
                stage_id=StageId(row["stage_id"]),
                stage_kind=StageKind(row["stage_kind"]),
                rubric_version=row["rubric_version"],
                turns=tuple(_turn(turn_row) for turn_row in turn_rows),
            )

        return await self._database.read(operation)

    async def renew(
        self,
        task_id: ScoreTaskId,
        *,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> ScoreTaskRecord:
        normalized_worker = worker_id.strip()
        if not normalized_worker or lease_duration <= timedelta(0):
            raise ValueError("worker_id and a positive lease_duration are required.")
        now_utc = now.astimezone(UTC)

        async def operation(connection: aiosqlite.Connection) -> ScoreTaskRecord:
            await _ensure_task_is_retained(connection, task_id, now_utc)
            row = await _fetchone(connection, "SELECT * FROM score_tasks WHERE id = ?", (task_id,))
            if row is None:
                raise ScoreTaskLeaseError(f"Unknown score task: {task_id}")
            task = _score_task(row)
            if (
                task.state is not ScoreTaskState.RUNNING
                or task.lease_owner != normalized_worker
                or task.lease_expires_at is None
                or task.lease_expires_at <= now_utc
            ):
                raise ScoreTaskLeaseError("Worker does not hold a current lease for this task.")
            await connection.execute(
                "UPDATE score_tasks SET lease_expires_at = ? WHERE id = ?",
                (_utc_text(now_utc + lease_duration), task_id),
            )
            renewed = await _fetchone(
                connection, "SELECT * FROM score_tasks WHERE id = ?", (task_id,)
            )
            if renewed is None:
                raise RuntimeError("Renewed score task disappeared.")
            return _score_task(renewed)

        return await self._database.write(operation)

    async def complete_with_result(
        self,
        task_id: ScoreTaskId,
        *,
        worker_id: str,
        completed_at: datetime,
        model: str,
        assessment: StageAssessment,
        summary: str | None,
    ) -> StageScoreRecord:
        normalized_worker = worker_id.strip()
        normalized_model = model.strip()
        if not normalized_worker or not normalized_model:
            raise ValueError("worker_id and model must not be blank.")

        async def operation(connection: aiosqlite.Connection) -> StageScoreRecord:
            await _ensure_task_is_retained(connection, task_id, completed_at)
            existing = await _load_stage_score(connection, task_id)
            row = await _fetchone(connection, "SELECT * FROM score_tasks WHERE id = ?", (task_id,))
            if row is None:
                raise ScoreTaskLeaseError(f"Unknown score task: {task_id}")
            task = _score_task(row)
            if existing is not None:
                if task.state is ScoreTaskState.SUCCEEDED:
                    return existing
                raise ScoreTaskLeaseError("A result exists for a task not marked succeeded.")
            if (
                task.state is not ScoreTaskState.RUNNING
                or task.lease_owner != normalized_worker
                or task.lease_expires_at is None
                or task.lease_expires_at <= completed_at.astimezone(UTC)
            ):
                raise ScoreTaskLeaseError("Worker does not hold a current lease for this task.")
            input_row = await _fetchone(
                connection,
                """
                SELECT s.stage_id FROM snapshots AS s
                WHERE s.id = ? AND s.rubric_version = ?
                """,
                (task.snapshot_id, assessment.rubric_version),
            )
            if input_row is None or assessment.rubric_version != task.rubric_version:
                raise ScoreTaskLeaseError("Assessment does not match the claimed snapshot rubric.")
            created_text = _utc_text(completed_at)
            await connection.execute(
                """
                INSERT INTO stage_scores(
                    task_id, snapshot_id, stage_id, rubric_version, model, average,
                    assessed_count, total_count, summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task.snapshot_id,
                    input_row["stage_id"],
                    assessment.rubric_version,
                    normalized_model,
                    assessment.average,
                    assessment.assessed_count,
                    assessment.total_count,
                    summary,
                    created_text,
                ),
            )
            for competency in assessment.competencies:
                if competency.status is None:
                    raise ValueError("Validated competency status must be explicit.")
                await connection.execute(
                    """
                    INSERT INTO competency_scores(
                        task_id, competency, status, score, rationale, limitation,
                        difficulty, assistance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        competency.competency,
                        competency.status.value,
                        competency.score,
                        competency.rationale,
                        competency.limitation,
                        competency.difficulty,
                        competency.assistance,
                    ),
                )
                for ordinal, citation in enumerate(competency.evidence):
                    await connection.execute(
                        """
                        INSERT INTO score_evidence(
                            task_id, competency, ordinal, turn_id, quote
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            task_id,
                            competency.competency,
                            ordinal,
                            citation.turn_id,
                            citation.quote,
                        ),
                    )
            await connection.execute(
                """
                UPDATE score_tasks
                SET state = ?, lease_owner = NULL, lease_expires_at = NULL,
                    failure = NULL, completed_at = ?
                WHERE id = ?
                """,
                (ScoreTaskState.SUCCEEDED.value, created_text, task_id),
            )
            stored = await _load_stage_score(connection, task_id)
            if stored is None:
                raise RuntimeError("Stored stage score disappeared.")
            return stored

        return await self._database.write(operation)

    async def fail(
        self,
        task_id: ScoreTaskId,
        *,
        worker_id: str,
        failed_at: datetime,
        failure: str,
        retry_at: datetime | None,
    ) -> ScoreTaskRecord:
        normalized_worker = worker_id.strip()
        normalized_failure = failure.strip()
        if not normalized_worker or not normalized_failure:
            raise ValueError("worker_id and failure must not be blank.")
        target = (
            ScoreTaskState.FAILED_RETRYABLE if retry_at is not None else ScoreTaskState.FAILED_FINAL
        )

        async def operation(connection: aiosqlite.Connection) -> ScoreTaskRecord:
            await _ensure_task_is_retained(connection, task_id, failed_at)
            row = await _fetchone(connection, "SELECT * FROM score_tasks WHERE id = ?", (task_id,))
            if row is None:
                raise ScoreTaskLeaseError(f"Unknown score task: {task_id}")
            task = _score_task(row)
            if (
                task.state is not ScoreTaskState.RUNNING
                or task.lease_owner != normalized_worker
                or task.lease_expires_at is None
                or task.lease_expires_at <= failed_at.astimezone(UTC)
            ):
                raise ScoreTaskLeaseError("Worker does not hold a current lease for this task.")
            available_at = retry_at or failed_at
            await connection.execute(
                """
                UPDATE score_tasks
                SET state = ?, lease_owner = NULL, lease_expires_at = NULL,
                    available_at = ?, failure = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    target.value,
                    _utc_text(available_at),
                    normalized_failure,
                    _utc_text(failed_at) if target is ScoreTaskState.FAILED_FINAL else None,
                    task_id,
                ),
            )
            failed = await _fetchone(
                connection, "SELECT * FROM score_tasks WHERE id = ?", (task_id,)
            )
            if failed is None:
                raise RuntimeError("Failed score task disappeared.")
            return _score_task(failed)

        return await self._database.write(operation)

    async def get_result(
        self,
        task_id: ScoreTaskId,
        *,
        now: datetime | None = None,
    ) -> StageScoreRecord | None:
        async def operation(connection: aiosqlite.Connection) -> StageScoreRecord | None:
            try:
                await _ensure_task_is_retained(connection, task_id, now or datetime.now(UTC))
            except ScoreTaskLeaseError:
                return None
            return await _load_stage_score(connection, task_id)

        return await self._database.read(operation)

    async def complete(
        self,
        task_id: ScoreTaskId,
        *,
        worker_id: str,
        completed_at: datetime,
    ) -> ScoreTaskRecord:
        normalized_worker = worker_id.strip()
        if not normalized_worker:
            raise ValueError("worker_id must not be blank.")
        completed_text = _utc_text(completed_at)

        async def operation(connection: aiosqlite.Connection) -> ScoreTaskRecord:
            await _ensure_task_is_retained(connection, task_id, completed_at)
            row = await _fetchone(connection, "SELECT * FROM score_tasks WHERE id = ?", (task_id,))
            if row is None:
                raise ScoreTaskLeaseError(f"Unknown score task: {task_id}")
            task = _score_task(row)
            if task.state is ScoreTaskState.SUCCEEDED:
                return task
            if (
                task.state is not ScoreTaskState.RUNNING
                or task.lease_owner != normalized_worker
                or task.lease_expires_at is None
                or task.lease_expires_at <= completed_at.astimezone(UTC)
            ):
                raise ScoreTaskLeaseError("Worker does not hold a current lease for this task.")
            await connection.execute(
                """
                UPDATE score_tasks
                SET state = ?, lease_owner = NULL, lease_expires_at = NULL, completed_at = ?
                WHERE id = ?
                """,
                (ScoreTaskState.SUCCEEDED.value, completed_text, task_id),
            )
            completed = await _fetchone(
                connection, "SELECT * FROM score_tasks WHERE id = ?", (task_id,)
            )
            if completed is None:
                raise RuntimeError("Completed score task disappeared.")
            return _score_task(completed)

        return await self._database.write(operation)


class SqliteRecoveryStore:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def save_checkpoint(self, checkpoint: RecoveryCheckpoint) -> None:
        async def operation(connection: aiosqlite.Connection) -> None:
            await _ensure_stage_is_retained(connection, checkpoint.stage_id, checkpoint.updated_at)
            await _upsert_checkpoint(connection, checkpoint)

        await self._database.write(operation)

    async def get_checkpoint(self, interview_id: InterviewId) -> RecoveryCheckpoint | None:
        async def operation(connection: aiosqlite.Connection) -> RecoveryCheckpoint | None:
            row = await _fetchone(
                connection,
                "SELECT * FROM recovery_checkpoints WHERE interview_id = ?",
                (interview_id,),
            )
            return _checkpoint(row) if row is not None else None

        return await self._database.read(operation)

    async def enter_recovery(
        self,
        checkpoint: RecoveryCheckpoint,
        *,
        expected: InterviewState,
    ) -> RecoveryCheckpoint:
        if expected is InterviewState.RECOVERING:
            raise ValueError("A new recovery incident needs a non-recovering source state.")

        async def operation(connection: aiosqlite.Connection) -> RecoveryCheckpoint:
            await _ensure_stage_is_retained(connection, checkpoint.stage_id, checkpoint.updated_at)
            cursor = await connection.execute(
                "UPDATE interviews SET state = ? WHERE id = ? AND state = ?",
                (InterviewState.RECOVERING.value, checkpoint.interview_id, expected.value),
            )
            if cursor.rowcount != 1:
                raise RecoveryStateError(
                    f"Interview {checkpoint.interview_id} was not in {expected.value}."
                )
            await _upsert_checkpoint(connection, checkpoint)
            return checkpoint

        return await self._database.write(operation)

    async def record_connection_attempt(self, attempt: ConnectionAttempt) -> None:
        async def operation(connection: aiosqlite.Connection) -> None:
            try:
                await connection.execute(
                    """
                    INSERT INTO connection_attempts(
                        id, interview_id, previous_room_sid, connected_room_sid,
                        attempted_at, succeeded, failure
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt.id,
                        attempt.interview_id,
                        attempt.previous_room_sid,
                        attempt.connected_room_sid,
                        _utc_text(attempt.attempted_at),
                        int(attempt.succeeded),
                        attempt.failure,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise RecoveryStateError(
                    f"Connection attempt cannot be recorded: {attempt.id}"
                ) from error

        await self._database.write(operation)

    async def resume(self, checkpoint: RecoveryCheckpoint) -> RecoveryCheckpoint:
        if checkpoint.recovery_deadline_at is not None:
            raise ValueError("A resumed checkpoint must clear its recovery deadline.")

        async def operation(connection: aiosqlite.Connection) -> RecoveryCheckpoint:
            await _ensure_stage_is_retained(connection, checkpoint.stage_id, checkpoint.updated_at)
            cursor = await connection.execute(
                """
                UPDATE interviews
                SET state = ?, room_sid = ?, incomplete_reason = NULL
                WHERE id = ? AND state = ?
                """,
                (
                    checkpoint.resumable_state.value,
                    checkpoint.room_sid,
                    checkpoint.interview_id,
                    InterviewState.RECOVERING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RecoveryStateError("Only a recovering interview can resume.")
            await _upsert_checkpoint(connection, checkpoint)
            return checkpoint

        return await self._database.write(operation)

    async def mark_incomplete(
        self,
        interview_id: InterviewId,
        *,
        reason: str,
        at: datetime,
    ) -> None:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("Incomplete reason must not be blank.")
        _utc_text(at)

        async def operation(connection: aiosqlite.Connection) -> None:
            cursor = await connection.execute(
                """
                UPDATE interviews SET state = ?, incomplete_reason = ?
                WHERE id = ? AND state NOT IN (?, ?)
                """,
                (
                    InterviewState.INCOMPLETE.value,
                    normalized_reason,
                    interview_id,
                    InterviewState.INTERVIEW_FINISHED.value,
                    InterviewState.INCOMPLETE.value,
                ),
            )
            if cursor.rowcount != 1:
                row = await _fetchone(
                    connection,
                    "SELECT state FROM interviews WHERE id = ?",
                    (interview_id,),
                )
                if row is None:
                    raise RecoveryStateError(f"Unknown interview: {interview_id}")
                if row["state"] != InterviewState.INCOMPLETE.value:
                    raise RecoveryStateError(
                        f"Terminal interview cannot be marked incomplete: {row['state']}"
                    )

        await self._database.write(operation)

    async def list_interrupted(self) -> tuple[InterruptedInterview, ...]:
        async def operation(connection: aiosqlite.Connection) -> tuple[InterruptedInterview, ...]:
            cutoff = _utc_text(_RETENTION_POLICY.expired_start_cutoff(now=datetime.now(UTC)))
            rows = await _fetchall(
                connection,
                """
                SELECT interview.*, checkpoint.interview_id AS checkpoint_interview_id,
                       checkpoint.stage_id, checkpoint.stage_kind,
                       checkpoint.resumable_state, checkpoint.remaining_active_seconds,
                       checkpoint.last_committed_turn_id,
                       checkpoint.last_committed_event_id,
                       checkpoint.interrupted_question_turn_id,
                       checkpoint.room_name AS checkpoint_room_name,
                       checkpoint.room_sid AS checkpoint_room_sid,
                       checkpoint.candidate_identity AS checkpoint_candidate_identity,
                       checkpoint.active_recording_segment_id,
                       checkpoint.recovery_started_at, checkpoint.recovery_deadline_at,
                       checkpoint.recovery_attempts, checkpoint.updated_at
                FROM interviews AS interview
                LEFT JOIN recovery_checkpoints AS checkpoint
                    ON checkpoint.interview_id = interview.id
                WHERE interview.state NOT IN (?, ?)
                  AND interview.created_at > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM deletion_jobs AS deletion
                      WHERE deletion.interview_id = interview.id
                  )
                ORDER BY interview.created_at, interview.id
                """,
                (
                    InterviewState.INTERVIEW_FINISHED.value,
                    InterviewState.INCOMPLETE.value,
                    cutoff,
                ),
            )
            return tuple(
                InterruptedInterview(
                    interview=_interview(row),
                    checkpoint=_checkpoint_from_join(row)
                    if row["checkpoint_interview_id"] is not None
                    else None,
                )
                for row in rows
            )

        return await self._database.read(operation)


class SqliteRetentionStore:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def prepare_expired(
        self,
        *,
        expired_at_or_before: datetime,
        prepared_at: datetime,
    ) -> tuple[DeletionJob, ...]:
        cutoff = _utc_text(expired_at_or_before)
        prepared = _utc_text(prepared_at)

        async def operation(connection: aiosqlite.Connection) -> tuple[DeletionJob, ...]:
            rows = await _fetchall(
                connection,
                """
                SELECT interview.id
                FROM interviews AS interview
                LEFT JOIN deletion_jobs AS deletion ON deletion.interview_id = interview.id
                WHERE interview.created_at <= ? AND deletion.interview_id IS NULL
                ORDER BY interview.created_at, interview.id
                """,
                (cutoff,),
            )
            jobs: list[DeletionJob] = []
            for row in rows:
                interview_id = InterviewId(row["id"])
                artifact_rows = await _fetchall(
                    connection,
                    """
                    SELECT segment.relative_path
                    FROM recording_segments AS segment
                    JOIN recordings AS recording ON recording.id = segment.recording_id
                    WHERE recording.interview_id = ?
                    ORDER BY segment.relative_path
                    """,
                    (interview_id,),
                )
                paths = {item["relative_path"] for item in artifact_rows}
                recording_rows = await _fetchall(
                    connection,
                    "SELECT id FROM recordings WHERE interview_id = ? ORDER BY id",
                    (interview_id,),
                )
                paths.update(f"{item['id']}/manifest.json" for item in recording_rows)
                artifact_paths = tuple(sorted(paths))
                await connection.execute(
                    """
                    INSERT INTO deletion_jobs(
                        interview_id, state, artifact_paths_json, failed_paths_json,
                        attempts, last_error, created_at, completed_at
                    ) VALUES (?, ?, ?, '[]', 0, NULL, ?, NULL)
                    """,
                    (
                        interview_id,
                        DeletionJobState.PENDING.value,
                        json.dumps(artifact_paths, separators=(",", ":")),
                        prepared,
                    ),
                )
                jobs.append(
                    DeletionJob(
                        interview_id=interview_id,
                        state=DeletionJobState.PENDING,
                        artifact_paths=artifact_paths,
                        failed_paths=(),
                        attempts=0,
                        last_error=None,
                        created_at=prepared_at.astimezone(UTC),
                        completed_at=None,
                    )
                )
            return tuple(jobs)

        return await self._database.write(operation)

    async def list_pending(self) -> tuple[DeletionJob, ...]:
        async def operation(connection: aiosqlite.Connection) -> tuple[DeletionJob, ...]:
            rows = await _fetchall(
                connection,
                """
                SELECT * FROM deletion_jobs WHERE state IN (?, ?)
                ORDER BY created_at, interview_id
                """,
                (DeletionJobState.PENDING.value, DeletionJobState.FILES_FAILED.value),
            )
            return tuple(_deletion_job(row) for row in rows)

        return await self._database.read(operation)

    async def record_file_failure(
        self,
        interview_id: InterviewId,
        *,
        failed_paths: tuple[str, ...],
        error: str,
    ) -> DeletionJob:
        normalized_error = error.strip()
        if not failed_paths or not normalized_error:
            raise ValueError("A file failure needs failed paths and an error.")

        async def operation(connection: aiosqlite.Connection) -> DeletionJob:
            cursor = await connection.execute(
                """
                UPDATE deletion_jobs
                SET state = ?, failed_paths_json = ?, attempts = attempts + 1, last_error = ?
                WHERE interview_id = ? AND state IN (?, ?)
                """,
                (
                    DeletionJobState.FILES_FAILED.value,
                    json.dumps(failed_paths, separators=(",", ":")),
                    normalized_error,
                    interview_id,
                    DeletionJobState.PENDING.value,
                    DeletionJobState.FILES_FAILED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"Unknown pending deletion job: {interview_id}")
            row = await _fetchone(
                connection,
                "SELECT * FROM deletion_jobs WHERE interview_id = ?",
                (interview_id,),
            )
            if row is None:
                raise RuntimeError("Failed deletion job disappeared.")
            return _deletion_job(row)

        return await self._database.write(operation)

    async def complete_deletion(
        self,
        interview_id: InterviewId,
        *,
        completed_at: datetime,
    ) -> DeletionJob:
        completed = _utc_text(completed_at)

        async def operation(connection: aiosqlite.Connection) -> DeletionJob:
            job_row = await _fetchone(
                connection,
                "SELECT * FROM deletion_jobs WHERE interview_id = ?",
                (interview_id,),
            )
            if job_row is None:
                raise LookupError(f"Unknown deletion job: {interview_id}")
            if job_row["state"] == DeletionJobState.COMPLETE.value:
                return _deletion_job(job_row)
            await connection.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))
            await connection.execute(
                """
                UPDATE deletion_jobs
                SET state = ?, artifact_paths_json = '[]', failed_paths_json = '[]',
                    attempts = attempts + 1, last_error = NULL, completed_at = ?
                WHERE interview_id = ?
                """,
                (DeletionJobState.COMPLETE.value, completed, interview_id),
            )
            row = await _fetchone(
                connection,
                "SELECT * FROM deletion_jobs WHERE interview_id = ?",
                (interview_id,),
            )
            if row is None:
                raise RuntimeError("Completed deletion receipt disappeared.")
            return _deletion_job(row)

        return await self._database.write(operation)


class SqliteRecordingManifestStore:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def save(self, manifest: RecordingManifest) -> None:
        gaps_by_segment = {
            segment.id: json.dumps(
                [
                    {
                        "offset_seconds": gap.offset_seconds,
                        "duration_seconds": gap.duration_seconds,
                        "reason": gap.reason,
                    }
                    for gap in segment.gaps
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for segment in manifest.segments
        }

        async def operation(connection: aiosqlite.Connection) -> None:
            existing = await _fetchone(
                connection, "SELECT id FROM recordings WHERE id = ?", (manifest.id,)
            )
            if existing is not None:
                stored = await _load_manifest(connection, manifest.id)
                if stored == manifest:
                    return
                raise RecordingLifecycleError(f"Recording manifest ID conflict: {manifest.id}")
            await connection.execute(
                """
                INSERT INTO recordings(
                    id, interview_id, sample_rate_hz, channels, sample_width_bytes,
                    started_at, completed_at, status, failure
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.id,
                    manifest.interview_id,
                    manifest.sample_rate_hz,
                    manifest.channels,
                    manifest.sample_width_bytes,
                    _utc_text(manifest.started_at),
                    _utc_text(manifest.completed_at),
                    manifest.status.value,
                    manifest.failure,
                ),
            )
            for segment in manifest.segments:
                await connection.execute(
                    """
                    INSERT INTO recording_segments(
                        id, recording_id, stage_id, speaker, relative_path,
                        offset_seconds, duration_seconds, checksum_sha256, status, gaps_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment.id,
                        segment.recording_id,
                        segment.stage_id,
                        segment.speaker.value,
                        segment.relative_path,
                        segment.offset_seconds,
                        segment.duration_seconds,
                        segment.checksum_sha256,
                        segment.status.value,
                        gaps_by_segment[segment.id],
                    ),
                )

        await self._database.write(operation)

    async def get(self, recording_id: RecordingId) -> RecordingManifest:
        async def operation(connection: aiosqlite.Connection) -> RecordingManifest:
            manifest = await _load_manifest(connection, recording_id)
            if manifest is None:
                raise RecordingLifecycleError(f"Unknown recording: {recording_id}")
            return manifest

        return await self._database.read(operation)


async def _fetchone(
    connection: aiosqlite.Connection,
    query: str,
    parameters: tuple[object, ...],
) -> aiosqlite.Row | None:
    cursor = await connection.execute(query, parameters)
    return await cursor.fetchone()


async def _fetchall(
    connection: aiosqlite.Connection,
    query: str,
    parameters: tuple[object, ...],
) -> list[aiosqlite.Row]:
    cursor = await connection.execute(query, parameters)
    return list(await cursor.fetchall())


async def _ensure_task_is_retained(
    connection: aiosqlite.Connection,
    task_id: ScoreTaskId,
    now: datetime,
) -> None:
    now_utc = now.astimezone(UTC)
    row = await _fetchone(
        connection,
        """
        SELECT interview.created_at,
               deletion.interview_id AS deletion_interview_id
        FROM score_tasks AS task
        JOIN snapshots AS snapshot ON snapshot.id = task.snapshot_id
        JOIN stages AS stage ON stage.id = snapshot.stage_id
        JOIN interviews AS interview ON interview.id = stage.interview_id
        LEFT JOIN deletion_jobs AS deletion ON deletion.interview_id = interview.id
        WHERE task.id = ?
        """,
        (task_id,),
    )
    if row is None:
        raise ScoreTaskLeaseError(f"Unknown score task: {task_id}")
    started_at = _datetime(row["created_at"])
    if started_at is None:
        raise ScoreTaskLeaseError("Score task interview has no start time.")
    if row["deletion_interview_id"] is not None or _RETENTION_POLICY.is_expired(
        started_at, now=now_utc
    ):
        raise ScoreTaskLeaseError("Score task belongs to an expired interview.")


async def _ensure_stage_is_retained(
    connection: aiosqlite.Connection,
    stage_id: StageId,
    now: datetime,
) -> None:
    row = await _fetchone(
        connection,
        """
        SELECT interview.created_at,
               deletion.interview_id AS deletion_interview_id
        FROM stages AS stage
        JOIN interviews AS interview ON interview.id = stage.interview_id
        LEFT JOIN deletion_jobs AS deletion ON deletion.interview_id = interview.id
        WHERE stage.id = ?
        """,
        (stage_id,),
    )
    if row is None:
        raise EvidenceConflictError(f"Unknown stage: {stage_id}")
    started_at = _datetime(row["created_at"])
    if started_at is None:
        raise EvidenceConflictError("Stage interview has no start time.")
    if row["deletion_interview_id"] is not None or _RETENTION_POLICY.is_expired(
        started_at, now=now
    ):
        raise EvidenceConflictError("Stage belongs to an expired interview.")


async def _upsert_checkpoint(
    connection: aiosqlite.Connection,
    checkpoint: RecoveryCheckpoint,
) -> None:
    if checkpoint.resumable_state not in {
        InterviewState.HR_ACTIVE,
        InterviewState.HR_DRAINING,
        InterviewState.HANDOFF,
        InterviewState.TECH_ACTIVE,
        InterviewState.TECH_DRAINING,
    }:
        raise ValueError("Checkpoint state is not resumable.")
    if checkpoint.remaining_active_seconds < 0:
        raise ValueError("Remaining active time must not be negative.")
    await connection.execute(
        """
        INSERT INTO recovery_checkpoints(
            interview_id, stage_id, stage_kind, resumable_state,
            remaining_active_seconds, last_committed_turn_id,
            last_committed_event_id, interrupted_question_turn_id,
            room_name, room_sid, candidate_identity, active_recording_segment_id,
            recovery_started_at, recovery_deadline_at, recovery_attempts, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(interview_id) DO UPDATE SET
            stage_id = excluded.stage_id,
            stage_kind = excluded.stage_kind,
            resumable_state = excluded.resumable_state,
            remaining_active_seconds = excluded.remaining_active_seconds,
            last_committed_turn_id = excluded.last_committed_turn_id,
            last_committed_event_id = excluded.last_committed_event_id,
            interrupted_question_turn_id = excluded.interrupted_question_turn_id,
            room_name = excluded.room_name,
            room_sid = excluded.room_sid,
            candidate_identity = excluded.candidate_identity,
            active_recording_segment_id = excluded.active_recording_segment_id,
            recovery_started_at = excluded.recovery_started_at,
            recovery_deadline_at = excluded.recovery_deadline_at,
            recovery_attempts = excluded.recovery_attempts,
            updated_at = excluded.updated_at
        """,
        (
            checkpoint.interview_id,
            checkpoint.stage_id,
            checkpoint.stage_kind.value,
            checkpoint.resumable_state.value,
            checkpoint.remaining_active_seconds,
            checkpoint.last_committed_turn_id,
            checkpoint.last_committed_event_id,
            checkpoint.interrupted_question_turn_id,
            checkpoint.room_name,
            checkpoint.room_sid,
            checkpoint.candidate_identity,
            checkpoint.active_recording_segment_id,
            _utc_text(checkpoint.recovery_started_at)
            if checkpoint.recovery_started_at is not None
            else None,
            _utc_text(checkpoint.recovery_deadline_at)
            if checkpoint.recovery_deadline_at is not None
            else None,
            checkpoint.recovery_attempts,
            _utc_text(checkpoint.updated_at),
        ),
    )


def _checkpoint(row: aiosqlite.Row) -> RecoveryCheckpoint:
    return _checkpoint_values(
        row,
        interview_id_key="interview_id",
        room_name_key="room_name",
        room_sid_key="room_sid",
        candidate_identity_key="candidate_identity",
    )


def _checkpoint_from_join(row: aiosqlite.Row) -> RecoveryCheckpoint:
    return _checkpoint_values(
        row,
        interview_id_key="checkpoint_interview_id",
        room_name_key="checkpoint_room_name",
        room_sid_key="checkpoint_room_sid",
        candidate_identity_key="checkpoint_candidate_identity",
    )


def _checkpoint_values(
    row: aiosqlite.Row,
    *,
    interview_id_key: str,
    room_name_key: str,
    room_sid_key: str,
    candidate_identity_key: str,
) -> RecoveryCheckpoint:
    updated_at = _datetime(row["updated_at"])
    if updated_at is None:
        raise ValueError("Recovery checkpoint updated_at must not be null.")
    return RecoveryCheckpoint(
        interview_id=InterviewId(row[interview_id_key]),
        stage_id=StageId(row["stage_id"]),
        stage_kind=StageKind(row["stage_kind"]),
        resumable_state=InterviewState(row["resumable_state"]),
        remaining_active_seconds=float(row["remaining_active_seconds"]),
        last_committed_turn_id=TurnId(row["last_committed_turn_id"])
        if row["last_committed_turn_id"] is not None
        else None,
        last_committed_event_id=EventId(row["last_committed_event_id"])
        if row["last_committed_event_id"] is not None
        else None,
        interrupted_question_turn_id=TurnId(row["interrupted_question_turn_id"])
        if row["interrupted_question_turn_id"] is not None
        else None,
        room_name=row[room_name_key],
        room_sid=row[room_sid_key],
        candidate_identity=row[candidate_identity_key],
        active_recording_segment_id=RecordingSegmentId(row["active_recording_segment_id"])
        if row["active_recording_segment_id"] is not None
        else None,
        recovery_started_at=_datetime(row["recovery_started_at"]),
        recovery_deadline_at=_datetime(row["recovery_deadline_at"]),
        recovery_attempts=int(row["recovery_attempts"]),
        updated_at=updated_at,
    )


def _deletion_job(row: aiosqlite.Row) -> DeletionJob:
    created_at = _datetime(row["created_at"])
    if created_at is None:
        raise ValueError("Deletion job created_at must not be null.")
    return DeletionJob(
        interview_id=InterviewId(row["interview_id"]),
        state=DeletionJobState(row["state"]),
        artifact_paths=tuple(json.loads(row["artifact_paths_json"])),
        failed_paths=tuple(json.loads(row["failed_paths_json"])),
        attempts=int(row["attempts"]),
        last_error=row["last_error"],
        created_at=created_at,
        completed_at=_datetime(row["completed_at"]),
    )


def _interview(row: aiosqlite.Row) -> InterviewRecord:
    created_at = _datetime(row["created_at"])
    if created_at is None:
        raise ValueError("Interview created_at must not be null.")
    return InterviewRecord(
        id=InterviewId(row["id"]),
        candidate_name=row["candidate_name"],
        state=InterviewState(row["state"]),
        created_at=created_at,
        room_name=row["room_name"],
        room_sid=row["room_sid"],
        candidate_identity=row["candidate_identity"],
    )


def _stage(row: aiosqlite.Row) -> StageRecord:
    created_at = _datetime(row["created_at"])
    if created_at is None:
        raise ValueError("Stage created_at must not be null.")
    return StageRecord(
        id=StageId(row["id"]),
        interview_id=InterviewId(row["interview_id"]),
        kind=StageKind(row["kind"]),
        state=StageState(row["state"]),
        created_at=created_at,
        session_reference=row["session_reference"],
    )


def _turn_values(turn: TurnRecord) -> tuple[object, ...]:
    return (
        turn.id,
        turn.stage_id,
        turn.speaker.value,
        turn.text,
        int(turn.is_final),
        turn.delivery_status.value,
        _utc_text(turn.occurred_at),
    )


def _turn(row: aiosqlite.Row) -> TurnRecord:
    occurred_at = _datetime(row["occurred_at"])
    if occurred_at is None:
        raise ValueError("Turn occurred_at must not be null.")
    return TurnRecord(
        id=TurnId(row["id"]),
        stage_id=StageId(row["stage_id"]),
        speaker=Speaker(row["speaker"]),
        text=row["text"],
        is_final=bool(row["is_final"]),
        delivery_status=DeliveryStatus(row["delivery_status"]),
        occurred_at=occurred_at,
    )


def _snapshot(row: aiosqlite.Row) -> TranscriptSnapshot:
    created_at = _datetime(row["created_at"])
    if created_at is None:
        raise ValueError("Snapshot created_at must not be null.")
    payload: list[dict[str, object]] = json.loads(row["content_json"])
    return TranscriptSnapshot(
        id=SnapshotId(row["id"]),
        stage_id=StageId(row["stage_id"]),
        rubric_version=row["rubric_version"],
        content_hash=row["content_hash"],
        turn_ids=tuple(TurnId(str(item["turn_id"])) for item in payload),
        created_at=created_at,
    )


def _score_task(row: aiosqlite.Row) -> ScoreTaskRecord:
    created_at = _datetime(row["created_at"])
    if created_at is None:
        raise ValueError("Score task created_at must not be null.")
    return ScoreTaskRecord(
        id=ScoreTaskId(row["id"]),
        snapshot_id=SnapshotId(row["snapshot_id"]),
        rubric_version=row["rubric_version"],
        state=ScoreTaskState(row["state"]),
        attempts=int(row["attempts"]),
        lease_owner=row["lease_owner"],
        lease_expires_at=_datetime(row["lease_expires_at"]),
        created_at=created_at,
        completed_at=_datetime(row["completed_at"]),
        failure=row["failure"],
    )


async def _load_stage_score(
    connection: aiosqlite.Connection, task_id: ScoreTaskId
) -> StageScoreRecord | None:
    row = await _fetchone(connection, "SELECT * FROM stage_scores WHERE task_id = ?", (task_id,))
    if row is None:
        return None
    competency_rows = await _fetchall(
        connection,
        "SELECT * FROM competency_scores WHERE task_id = ? ORDER BY rowid",
        (task_id,),
    )
    competencies: list[CompetencyAssessment] = []
    for competency_row in competency_rows:
        evidence_rows = await _fetchall(
            connection,
            """
            SELECT turn_id, quote FROM score_evidence
            WHERE task_id = ? AND competency = ? ORDER BY ordinal
            """,
            (task_id, competency_row["competency"]),
        )
        competencies.append(
            CompetencyAssessment(
                competency=competency_row["competency"],
                score=competency_row["score"],
                rationale=competency_row["rationale"],
                evidence=tuple(
                    EvidenceCitation(turn_id=TurnId(item["turn_id"]), quote=item["quote"])
                    for item in evidence_rows
                ),
                limitation=competency_row["limitation"],
                status=AssessmentStatus(competency_row["status"]),
                difficulty=competency_row["difficulty"],
                assistance=competency_row["assistance"],
            )
        )
    created_at = _datetime(row["created_at"])
    if created_at is None:
        raise ValueError("Stage score created_at must not be null.")
    return StageScoreRecord(
        task_id=ScoreTaskId(row["task_id"]),
        snapshot_id=SnapshotId(row["snapshot_id"]),
        stage_id=StageId(row["stage_id"]),
        rubric_version=row["rubric_version"],
        model=row["model"],
        assessment=StageAssessment(
            rubric_version=row["rubric_version"],
            competencies=tuple(competencies),
            average=row["average"],
            assessed_count=int(row["assessed_count"]),
            total_count=int(row["total_count"]),
        ),
        summary=row["summary"],
        created_at=created_at,
    )


async def _load_manifest(
    connection: aiosqlite.Connection, recording_id: RecordingId
) -> RecordingManifest | None:
    row = await _fetchone(connection, "SELECT * FROM recordings WHERE id = ?", (recording_id,))
    if row is None:
        return None
    segment_rows = await _fetchall(
        connection,
        "SELECT * FROM recording_segments WHERE recording_id = ? ORDER BY offset_seconds, id",
        (recording_id,),
    )
    segments = []
    for segment_row in segment_rows:
        gap_payload: list[dict[str, object]] = json.loads(segment_row["gaps_json"])
        gaps = tuple(
            RecordingGap(
                offset_seconds=float(str(item["offset_seconds"])),
                duration_seconds=float(str(item["duration_seconds"])),
                reason=str(item["reason"]),
            )
            for item in gap_payload
        )
        segments.append(
            RecordingSegment(
                id=RecordingSegmentId(segment_row["id"]),
                recording_id=RecordingId(segment_row["recording_id"]),
                stage_id=StageId(segment_row["stage_id"]),
                speaker=Speaker(segment_row["speaker"]),
                relative_path=segment_row["relative_path"],
                offset_seconds=float(segment_row["offset_seconds"]),
                duration_seconds=float(segment_row["duration_seconds"]),
                checksum_sha256=segment_row["checksum_sha256"],
                status=RecordingStatus(segment_row["status"]),
                gaps=gaps,
            )
        )
    started_at = _datetime(row["started_at"])
    completed_at = _datetime(row["completed_at"])
    if started_at is None or completed_at is None:
        raise ValueError("Recording timestamps must not be null.")
    return RecordingManifest(
        id=RecordingId(row["id"]),
        interview_id=InterviewId(row["interview_id"]),
        sample_rate_hz=int(row["sample_rate_hz"]),
        channels=int(row["channels"]),
        sample_width_bytes=int(row["sample_width_bytes"]),
        started_at=started_at,
        completed_at=completed_at,
        status=RecordingStatus(row["status"]),
        failure=row["failure"],
        segments=tuple(segments),
    )
