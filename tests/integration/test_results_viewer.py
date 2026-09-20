import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from interview_app.adapters.fakes import FakeClock
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecordingManifestStore,
    SqliteResultsReader,
    SqliteScoreTaskStore,
    SqliteTranscriptStore,
)
from interview_app.adapters.web import ResultsHttpApplication
from interview_app.application.results import InterviewResult
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
    ScoreTaskState,
    Speaker,
    StageId,
    StageKind,
    StageRecord,
    StageState,
    TurnId,
    TurnRecord,
)
from interview_app.domain.scoring import (
    AssessmentStatus,
    CompetencyAssessment,
    EvidenceCitation,
    StageAssessment,
)
from interview_app.resources.rubrics import HR_RUBRIC_V1, TECHNICAL_RUBRIC_V1

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
MALICIOUS_NAME = 'Alex <script>alert("candidate")</script>'
MALICIOUS_TEXT = '<img src=x onerror="alert(1)"> concrete answer'


async def _seed_results(database: SqliteDatabase, recordings_root: Path) -> dict[str, str]:
    await database.migrate()
    interviews = SqliteInterviewStore(database)
    transcripts = SqliteTranscriptStore(database)

    interview_id = InterviewId("visible-interview")
    hr_stage_id = StageId("visible-hr")
    technical_stage_id = StageId("visible-technical")
    answer_id = TurnId("visible-answer")
    await interviews.create(
        InterviewRecord(
            id=interview_id,
            candidate_name=MALICIOUS_NAME,
            state=InterviewState.TECH_ACTIVE,
            created_at=NOW - timedelta(hours=1),
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=hr_stage_id,
            interview_id=interview_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=NOW - timedelta(hours=1),
        )
    )
    await transcripts.append_turn(
        TurnRecord(
            id=answer_id,
            stage_id=hr_stage_id,
            speaker=Speaker.CANDIDATE,
            text=MALICIOUS_TEXT,
            is_final=True,
            delivery_status=DeliveryStatus.DELIVERED,
            occurred_at=NOW - timedelta(minutes=59),
        )
    )
    _, hr_task = await transcripts.finalize_snapshot_and_enqueue(
        hr_stage_id,
        rubric_version=HR_RUBRIC_V1.version,
        created_at=NOW - timedelta(minutes=58),
    )
    await transcripts.create_stage(
        StageRecord(
            id=technical_stage_id,
            interview_id=interview_id,
            kind=StageKind.TECHNICAL,
            state=StageState.ACTIVE,
            created_at=NOW - timedelta(minutes=57),
        )
    )
    await transcripts.finalize_snapshot_and_enqueue(
        technical_stage_id,
        rubric_version=TECHNICAL_RUBRIC_V1.version,
        created_at=NOW - timedelta(minutes=56),
    )

    tasks = SqliteScoreTaskStore(database)
    claimed = await tasks.claim_next(
        worker_id="results-test",
        now=NOW - timedelta(minutes=55),
        lease_duration=timedelta(minutes=10),
    )
    assert claimed is not None and claimed.id == hr_task.id
    competencies = tuple(
        CompetencyAssessment(
            competency=item.key,
            score=4 if index == 0 else None,
            rationale=(
                '<b onclick="alert(2)">Supported by a concrete answer.</b>'
                if index == 0
                else "Not covered."
            ),
            evidence=(
                (EvidenceCitation(turn_id=answer_id, quote="concrete answer"),)
                if index == 0
                else ()
            ),
            limitation=None if index == 0 else "No evidence captured.",
            status=(
                AssessmentStatus.ASSESSED if index == 0 else AssessmentStatus.INSUFFICIENT_EVIDENCE
            ),
            difficulty="Intermediate <svg onload=alert(3)>" if index == 0 else None,
            assistance="One hint <script>alert(4)</script>" if index == 0 else None,
        )
        for index, item in enumerate(HR_RUBRIC_V1.competencies)
    )
    await tasks.complete_with_result(
        hr_task.id,
        worker_id="results-test",
        completed_at=NOW - timedelta(minutes=54),
        model="offline/test",
        assessment=StageAssessment(
            rubric_version=HR_RUBRIC_V1.version,
            competencies=competencies,
            average=4.0,
            assessed_count=1,
            total_count=4,
        ),
        summary='<script>alert("summary")</script>',
    )

    recording_id = RecordingId("visible-recording")
    segment_id = RecordingSegmentId("visible-segment")
    relative_path = f"{recording_id}/{segment_id}.wav"
    media = b"RIFFsynthetic-wave"
    media_path = recordings_root / relative_path
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(media)
    await SqliteRecordingManifestStore(database).save(
        RecordingManifest(
            id=recording_id,
            interview_id=interview_id,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            started_at=NOW - timedelta(hours=1),
            completed_at=NOW - timedelta(minutes=54),
            status=RecordingStatus.INCOMPLETE,
            failure="Synthetic gap",
            segments=(
                RecordingSegment(
                    id=segment_id,
                    recording_id=recording_id,
                    stage_id=hr_stage_id,
                    speaker=Speaker.CANDIDATE,
                    relative_path=relative_path,
                    offset_seconds=1.5,
                    duration_seconds=3.0,
                    checksum_sha256=hashlib.sha256(media).hexdigest(),
                    status=RecordingStatus.INCOMPLETE,
                    gaps=(),
                ),
            ),
        )
    )

    duplicate_id = InterviewId("duplicate-incomplete")
    duplicate_stage = StageId("duplicate-stage")
    await interviews.create(
        InterviewRecord(
            id=duplicate_id,
            candidate_name=MALICIOUS_NAME,
            state=InterviewState.INCOMPLETE,
            created_at=NOW - timedelta(hours=2),
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=duplicate_stage,
            interview_id=duplicate_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=NOW - timedelta(hours=2),
        )
    )
    _, failed_task = await transcripts.finalize_snapshot_and_enqueue(
        duplicate_stage,
        rubric_version=HR_RUBRIC_V1.version,
        created_at=NOW - timedelta(hours=2),
    )

    async def mark_failed(connection: aiosqlite.Connection) -> None:
        await connection.execute(
            "UPDATE score_tasks SET state = ?, failure = ?, completed_at = ? WHERE id = ?",
            (
                ScoreTaskState.FAILED_FINAL.value,
                '<script>alert("failure")</script>',
                NOW.isoformat(),
                failed_task.id,
            ),
        )

    await database.write(mark_failed)

    expired_id = InterviewId("expired-interview")
    expired_stage = StageId("expired-stage")
    await interviews.create(
        InterviewRecord(
            id=expired_id,
            candidate_name="Expired Candidate",
            state=InterviewState.INTERVIEW_FINISHED,
            created_at=NOW - timedelta(days=30),
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=expired_stage,
            interview_id=expired_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=NOW - timedelta(days=30),
        )
    )
    expired_recording = RecordingId("expired-recording")
    expired_segment = RecordingSegmentId("expired-segment")
    await SqliteRecordingManifestStore(database).save(
        RecordingManifest(
            id=expired_recording,
            interview_id=expired_id,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            started_at=NOW - timedelta(days=30),
            completed_at=NOW - timedelta(days=30),
            status=RecordingStatus.COMPLETE,
            failure=None,
            segments=(
                RecordingSegment(
                    id=expired_segment,
                    recording_id=expired_recording,
                    stage_id=expired_stage,
                    speaker=Speaker.CANDIDATE,
                    relative_path="expired-recording/expired.wav",
                    offset_seconds=0,
                    duration_seconds=1,
                    checksum_sha256="0" * 64,
                    status=RecordingStatus.COMPLETE,
                    gaps=(),
                ),
            ),
        )
    )
    return {
        "interview_id": str(interview_id),
        "duplicate_id": str(duplicate_id),
        "segment_id": str(segment_id),
        "expired_id": str(expired_id),
        "expired_segment": str(expired_segment),
        "media": media.decode("ascii"),
    }


def test_results_reader_keeps_duplicate_names_and_stage_assessments_separate(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "results.sqlite3")
        identifiers = await _seed_results(database, tmp_path / "recordings")
        reader = SqliteResultsReader(database)

        summaries = await reader.list_interviews(now=NOW)
        assert [item.id for item in summaries] == [
            InterviewId(identifiers["interview_id"]),
            InterviewId(identifiers["duplicate_id"]),
        ]
        assert summaries[0].candidate_name == summaries[1].candidate_name
        assert summaries[0].stages[0].average == 4.0
        assert summaries[0].stages[0].assessed_count == 1
        assert summaries[0].stages[1].assessment_state is ScoreTaskState.PENDING
        assert summaries[1].state is InterviewState.INCOMPLETE
        assert summaries[1].stages[0].assessment_state is ScoreTaskState.FAILED_FINAL

        detail = await reader.get_interview(InterviewId(identifiers["interview_id"]), now=NOW)
        assert isinstance(detail, InterviewResult)
        assert [stage.kind for stage in detail.stages] == [StageKind.HR, StageKind.TECHNICAL]
        assert detail.stages[0].assessment is not None
        assert detail.stages[0].assessment.competencies[0].evidence[0].turn_id == TurnId(
            "visible-answer"
        )

    asyncio.run(exercise())


def test_results_html_escapes_untrusted_text_and_media_is_id_authorized(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "results.sqlite3")
        recordings_root = tmp_path / "recordings"
        identifiers = await _seed_results(database, recordings_root)
        application = ResultsHttpApplication(
            reader=SqliteResultsReader(database),
            recordings_root=recordings_root,
            clock=FakeClock(now=NOW),
        )

        listing = await application.handle("GET", "/results")
        assert listing.status == 200
        assert MALICIOUS_NAME not in listing.body.decode()
        assert "&lt;script&gt;alert" in listing.body.decode()

        detail = await application.handle("GET", f"/results/{identifiers['interview_id']}")
        document = detail.body.decode()
        assert detail.status == 200
        assert MALICIOUS_TEXT not in document
        assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in document
        assert '<script>alert("summary")</script>' not in document
        assert "HR and technical assessments are independent" in document
        assert 'href="#turn-visible-answer"' in document
        assert "Observed difficulty" in document and "Hints/assistance" in document
        assert "Score: pending; coverage: pending" in document
        assert "Recording issue: Synthetic gap" in document
        assert "form" not in document.lower()

        failed = await application.handle("GET", f"/results/{identifiers['duplicate_id']}")
        failed_document = failed.body.decode()
        assert failed.status == 200
        assert '<script>alert("failure")</script>' not in failed_document
        assert "&lt;script&gt;alert(&quot;failure&quot;)&lt;/script&gt;" in failed_document

        media = await application.handle("GET", f"/media/{identifiers['segment_id']}")
        assert media.status == 200
        assert media.body == identifiers["media"].encode()
        assert media.headers["Content-Type"] == "audio/wav"

        (recordings_root / "visible-recording" / "visible-segment.wav").unlink()
        missing = await application.handle("GET", f"/media/{identifiers['segment_id']}")
        expired_result = await application.handle("GET", f"/results/{identifiers['expired_id']}")
        expired_media = await application.handle("GET", f"/media/{identifiers['expired_segment']}")
        traversal = await application.handle("GET", "/media/../../.env")
        write_attempt = await application.handle("POST", "/results")
        assert missing.status == 404
        assert expired_result.status == 404
        assert expired_media.status == 404
        assert traversal.status == 404
        assert write_attempt.status == 405

    asyncio.run(exercise())
