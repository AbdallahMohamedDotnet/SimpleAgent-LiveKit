"""Read-only SQLite projection for local interview results."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite

from interview_app.adapters.sqlite.database import SqliteDatabase
from interview_app.application.ports.results import ResultNotFoundError
from interview_app.application.results import (
    AssessmentResult,
    CompetencyResult,
    InterviewResult,
    InterviewSummary,
    MediaRecord,
    RecordingGapResult,
    RecordingResult,
    ResultEvidence,
    ResultTurn,
    StageResult,
    StageSummary,
)
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewState,
    RecordingSegmentId,
    RecordingStatus,
    ScoreTaskState,
    Speaker,
    StageId,
    StageKind,
    StageState,
    TurnId,
)
from interview_app.domain.policies import RetentionPolicy
from interview_app.domain.scoring import AssessmentStatus


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Result query timestamps must be timezone-aware.")
    return value.astimezone(UTC).isoformat()


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqliteResultsReader:
    """Build presentation DTOs without exposing SQL or write methods to consumers."""

    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database
        self._retention = RetentionPolicy()

    async def list_interviews(self, *, now: datetime) -> tuple[InterviewSummary, ...]:
        cutoff = _utc_text(self._retention.expired_start_cutoff(now=now))

        async def operation(connection: aiosqlite.Connection) -> tuple[InterviewSummary, ...]:
            interview_rows = await _fetchall(
                connection,
                """
                SELECT interview.id, interview.candidate_name, interview.state,
                       interview.created_at
                FROM interviews AS interview
                WHERE interview.created_at > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM deletion_jobs AS deletion
                      WHERE deletion.interview_id = interview.id
                  )
                ORDER BY interview.created_at DESC, interview.id
                """,
                (cutoff,),
            )
            summaries: list[InterviewSummary] = []
            for interview_row in interview_rows:
                stage_rows = await _fetchall(
                    connection,
                    """
                    SELECT stage.kind, stage.state,
                           task.state AS assessment_state,
                           score.average, score.assessed_count, score.total_count
                    FROM stages AS stage
                    LEFT JOIN snapshots AS snapshot ON snapshot.id = (
                        SELECT candidate.id FROM snapshots AS candidate
                        WHERE candidate.stage_id = stage.id
                        ORDER BY candidate.created_at DESC, candidate.id DESC LIMIT 1
                    )
                    LEFT JOIN score_tasks AS task ON task.snapshot_id = snapshot.id
                    LEFT JOIN stage_scores AS score ON score.task_id = task.id
                    WHERE stage.interview_id = ?
                    ORDER BY CASE stage.kind WHEN 'hr' THEN 0 ELSE 1 END, stage.created_at
                    """,
                    (interview_row["id"],),
                )
                summaries.append(
                    InterviewSummary(
                        id=InterviewId(interview_row["id"]),
                        candidate_name=interview_row["candidate_name"],
                        state=InterviewState(interview_row["state"]),
                        created_at=_datetime(interview_row["created_at"]),
                        stages=tuple(_stage_summary(row) for row in stage_rows),
                    )
                )
            return tuple(summaries)

        return await self._database.read(operation)

    async def get_interview(
        self,
        interview_id: InterviewId,
        *,
        now: datetime,
    ) -> InterviewResult:
        cutoff = _utc_text(self._retention.expired_start_cutoff(now=now))

        async def operation(connection: aiosqlite.Connection) -> InterviewResult:
            interview_row = await _fetchone(
                connection,
                """
                SELECT interview.id, interview.candidate_name, interview.state,
                       interview.created_at
                FROM interviews AS interview
                WHERE interview.id = ? AND interview.created_at > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM deletion_jobs AS deletion
                      WHERE deletion.interview_id = interview.id
                  )
                """,
                (interview_id, cutoff),
            )
            if interview_row is None:
                raise ResultNotFoundError(f"Unknown or expired interview: {interview_id}")
            stage_rows = await _fetchall(
                connection,
                """
                SELECT id, kind, state FROM stages WHERE interview_id = ?
                ORDER BY CASE kind WHEN 'hr' THEN 0 ELSE 1 END, created_at, id
                """,
                (interview_id,),
            )
            stages = tuple([await _load_stage(connection, stage_row) for stage_row in stage_rows])
            return InterviewResult(
                id=InterviewId(interview_row["id"]),
                candidate_name=interview_row["candidate_name"],
                state=InterviewState(interview_row["state"]),
                created_at=_datetime(interview_row["created_at"]),
                stages=stages,
            )

        return await self._database.read(operation)

    async def get_media(
        self,
        segment_id: RecordingSegmentId,
        *,
        now: datetime,
    ) -> MediaRecord:
        cutoff = _utc_text(self._retention.expired_start_cutoff(now=now))

        async def operation(connection: aiosqlite.Connection) -> MediaRecord:
            row = await _fetchone(
                connection,
                """
                SELECT segment.id, segment.relative_path, segment.checksum_sha256,
                       segment.status
                FROM recording_segments AS segment
                JOIN recordings AS recording ON recording.id = segment.recording_id
                JOIN interviews AS interview ON interview.id = recording.interview_id
                WHERE segment.id = ? AND interview.created_at > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM deletion_jobs AS deletion
                      WHERE deletion.interview_id = interview.id
                  )
                """,
                (segment_id, cutoff),
            )
            if row is None:
                raise ResultNotFoundError(f"Unknown or expired media: {segment_id}")
            return MediaRecord(
                segment_id=RecordingSegmentId(row["id"]),
                relative_path=row["relative_path"],
                checksum_sha256=row["checksum_sha256"],
                status=RecordingStatus(row["status"]),
            )

        return await self._database.read(operation)


async def _load_stage(connection: aiosqlite.Connection, row: aiosqlite.Row) -> StageResult:
    stage_id = StageId(row["id"])
    turn_rows = await _fetchall(
        connection,
        """
        SELECT id, speaker, text, delivery_status, occurred_at
        FROM turns WHERE stage_id = ? AND is_final = 1 ORDER BY occurred_at, id
        """,
        (stage_id,),
    )
    task_row = await _fetchone(
        connection,
        """
        SELECT task.id, task.state, task.failure,
               score.average, score.assessed_count, score.total_count, score.summary
        FROM snapshots AS snapshot
        JOIN score_tasks AS task ON task.snapshot_id = snapshot.id
        LEFT JOIN stage_scores AS score ON score.task_id = task.id
        WHERE snapshot.stage_id = ?
        ORDER BY snapshot.created_at DESC, snapshot.id DESC LIMIT 1
        """,
        (stage_id,),
    )
    assessment = await _load_assessment(connection, task_row) if task_row is not None else None
    recording_rows = await _fetchall(
        connection,
        """
        SELECT segment.id, segment.speaker, segment.status, segment.offset_seconds,
               segment.duration_seconds, segment.gaps_json,
               recording.failure AS recording_failure
        FROM recording_segments AS segment
        JOIN recordings AS recording ON recording.id = segment.recording_id
        WHERE segment.stage_id = ? ORDER BY segment.offset_seconds, segment.id
        """,
        (stage_id,),
    )
    return StageResult(
        id=stage_id,
        kind=StageKind(row["kind"]),
        state=StageState(row["state"]),
        turns=tuple(
            ResultTurn(
                id=TurnId(turn["id"]),
                speaker=Speaker(turn["speaker"]),
                text=turn["text"],
                delivery_status=DeliveryStatus(turn["delivery_status"]),
                occurred_at=_datetime(turn["occurred_at"]),
            )
            for turn in turn_rows
        ),
        assessment=assessment,
        recordings=tuple(_recording_result(recording) for recording in recording_rows),
    )


async def _load_assessment(
    connection: aiosqlite.Connection,
    row: aiosqlite.Row,
) -> AssessmentResult:
    competency_rows = await _fetchall(
        connection,
        """
        SELECT competency, status, score, rationale, limitation, difficulty, assistance
        FROM competency_scores WHERE task_id = ? ORDER BY rowid
        """,
        (row["id"],),
    )
    competencies: list[CompetencyResult] = []
    for competency in competency_rows:
        evidence_rows = await _fetchall(
            connection,
            """
            SELECT turn_id, quote FROM score_evidence
            WHERE task_id = ? AND competency = ? ORDER BY ordinal
            """,
            (row["id"], competency["competency"]),
        )
        competencies.append(
            CompetencyResult(
                name=competency["competency"],
                status=AssessmentStatus(competency["status"]),
                score=int(competency["score"]) if competency["score"] is not None else None,
                rationale=competency["rationale"],
                limitation=competency["limitation"],
                difficulty=competency["difficulty"],
                assistance=competency["assistance"],
                evidence=tuple(
                    ResultEvidence(turn_id=TurnId(item["turn_id"]), quote=item["quote"])
                    for item in evidence_rows
                ),
            )
        )
    return AssessmentResult(
        state=ScoreTaskState(row["state"]),
        average=float(row["average"]) if row["average"] is not None else None,
        assessed_count=(int(row["assessed_count"]) if row["assessed_count"] is not None else None),
        total_count=int(row["total_count"]) if row["total_count"] is not None else None,
        summary=row["summary"],
        failure=row["failure"],
        competencies=tuple(competencies),
    )


def _stage_summary(row: aiosqlite.Row) -> StageSummary:
    return StageSummary(
        kind=StageKind(row["kind"]),
        state=StageState(row["state"]),
        assessment_state=(
            ScoreTaskState(row["assessment_state"]) if row["assessment_state"] is not None else None
        ),
        average=float(row["average"]) if row["average"] is not None else None,
        assessed_count=(int(row["assessed_count"]) if row["assessed_count"] is not None else None),
        total_count=int(row["total_count"]) if row["total_count"] is not None else None,
    )


def _recording_result(row: aiosqlite.Row) -> RecordingResult:
    gaps: list[dict[str, object]] = json.loads(row["gaps_json"])
    return RecordingResult(
        segment_id=RecordingSegmentId(row["id"]),
        speaker=Speaker(row["speaker"]),
        status=RecordingStatus(row["status"]),
        offset_seconds=float(row["offset_seconds"]),
        duration_seconds=float(row["duration_seconds"]),
        manifest_failure=row["recording_failure"],
        gaps=tuple(
            RecordingGapResult(
                offset_seconds=_json_number(gap["offset_seconds"]),
                duration_seconds=_json_number(gap["duration_seconds"]),
                reason=str(gap["reason"]),
            )
            for gap in gaps
        ),
    )


def _json_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Recording gap values must be numeric.")
    return float(value)


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
