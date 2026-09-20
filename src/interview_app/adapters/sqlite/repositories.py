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
from interview_app.application.ports.score_task_store import ScoreTaskLeaseError
from interview_app.application.ports.transcript_store import EvidenceConflictError
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
    RecordingGap,
    RecordingId,
    RecordingManifest,
    RecordingSegment,
    RecordingSegmentId,
    RecordingStatus,
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


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Persisted timestamps must be timezone-aware.")
    return value.astimezone(UTC).isoformat()


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


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

    async def get(self, interview_id: InterviewId) -> InterviewRecord:
        async def operation(connection: aiosqlite.Connection) -> InterviewRecord:
            row = await _fetchone(
                connection,
                "SELECT * FROM interviews WHERE id = ?",
                (interview_id,),
            )
            if row is None:
                raise InterviewNotFoundError(f"Unknown interview: {interview_id}")
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
            cursor = await connection.execute(
                "UPDATE interviews SET state = ? WHERE id = ? AND state = ?",
                (target.value, interview_id, expected.value),
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
                SELECT id FROM score_tasks
                WHERE
                    (state = ? AND available_at <= ?)
                    OR (state = ? AND lease_expires_at <= ?)
                ORDER BY created_at, id
                LIMIT 1
                """,
                (
                    ScoreTaskState.PENDING.value,
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
