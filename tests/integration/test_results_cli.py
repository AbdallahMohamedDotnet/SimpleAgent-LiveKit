import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite
import pytest

from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecordingManifestStore,
    SqliteResultsReader,
    SqliteScoreTaskStore,
    SqliteTranscriptStore,
)
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
from interview_app.entrypoints import cli
from interview_app.resources.rubrics import HR_RUBRIC_V1, TECHNICAL_RUBRIC_V1

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
ESCAPE = "\x1b"
MALICIOUS_NAME = f'Alex {ESCAPE}[2J{ESCAPE}[1;31m<script>alert("candidate")</script>'
MALICIOUS_TEXT = f"{ESCAPE}]0;spoofed-title\x07 concrete answer"


async def _seed_results(
    database: SqliteDatabase,
    recordings_root: Path,
    now: datetime = NOW,
) -> dict[str, str]:
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
            created_at=now - timedelta(hours=1),
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=hr_stage_id,
            interview_id=interview_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=now - timedelta(hours=1),
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
            occurred_at=now - timedelta(minutes=59),
        )
    )
    _, hr_task = await transcripts.finalize_snapshot_and_enqueue(
        hr_stage_id,
        rubric_version=HR_RUBRIC_V1.version,
        created_at=now - timedelta(minutes=58),
    )
    await transcripts.create_stage(
        StageRecord(
            id=technical_stage_id,
            interview_id=interview_id,
            kind=StageKind.TECHNICAL,
            state=StageState.ACTIVE,
            created_at=now - timedelta(minutes=57),
        )
    )
    await transcripts.finalize_snapshot_and_enqueue(
        technical_stage_id,
        rubric_version=TECHNICAL_RUBRIC_V1.version,
        created_at=now - timedelta(minutes=56),
    )

    tasks = SqliteScoreTaskStore(database)
    claimed = await tasks.claim_next(
        worker_id="results-test",
        now=now - timedelta(minutes=55),
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
        completed_at=now - timedelta(minutes=54),
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
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(minutes=54),
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
            created_at=now - timedelta(hours=2),
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=duplicate_stage,
            interview_id=duplicate_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=now - timedelta(hours=2),
        )
    )
    _, failed_task = await transcripts.finalize_snapshot_and_enqueue(
        duplicate_stage,
        rubric_version=HR_RUBRIC_V1.version,
        created_at=now - timedelta(hours=2),
    )

    async def mark_failed(connection: aiosqlite.Connection) -> None:
        await connection.execute(
            "UPDATE score_tasks SET state = ?, failure = ?, completed_at = ? WHERE id = ?",
            (
                ScoreTaskState.FAILED_FINAL.value,
                '<script>alert("failure")</script>',
                now.isoformat(),
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
            created_at=now - timedelta(days=30),
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=expired_stage,
            interview_id=expired_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=now - timedelta(days=30),
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
            started_at=now - timedelta(days=30),
            completed_at=now - timedelta(days=30),
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


@pytest.fixture
def seeded_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    """Seed a temporary store and point the CLI at it without reading the repository .env."""
    recordings_root = tmp_path / "recordings"
    database = SqliteDatabase(tmp_path / "results.sqlite3")
    identifiers = asyncio.run(_seed_results(database, recordings_root, now=datetime.now(UTC)))
    asyncio.run(_seed_traversal_segment(database, identifiers["interview_id"]))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "results.sqlite3"))
    monkeypatch.setenv("RECORDINGS_DIR", str(recordings_root))
    return identifiers


async def _seed_traversal_segment(database: SqliteDatabase, interview_id: str) -> None:
    """Record a segment whose stored path escapes the owned root, as a tampered store would."""
    await SqliteRecordingManifestStore(database).save(
        RecordingManifest(
            id=RecordingId("traversal-recording"),
            interview_id=InterviewId(interview_id),
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status=RecordingStatus.COMPLETE,
            failure=None,
            segments=(
                RecordingSegment(
                    id=RecordingSegmentId("traversal-segment"),
                    recording_id=RecordingId("traversal-recording"),
                    stage_id=StageId("visible-hr"),
                    speaker=Speaker.CANDIDATE,
                    relative_path="../../.env",
                    offset_seconds=0,
                    duration_seconds=1,
                    checksum_sha256="0" * 64,
                    status=RecordingStatus.COMPLETE,
                    gaps=(),
                ),
            ),
        )
    )


def test_results_list_and_show_report_stages_independently(
    seeded_cli: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["results", "list"]) == 0
    listing = capsys.readouterr().out
    assert "retained_interviews=2" in listing
    assert f"interview_id={seeded_cli['interview_id']}" in listing
    assert seeded_cli["expired_id"] not in listing
    assert "stage=hr conversation=closed assessment=succeeded score=4.00/5 coverage=1/4" in listing
    assert (
        "stage=technical conversation=active assessment=pending score=pending coverage=pending"
        in listing
    )

    assert cli.main(["results", "show", "--interview-id", seeded_cli["interview_id"]]) == 0
    detail = capsys.readouterr().out
    assert "HR and technical assessments are independent" in detail
    assert "stage=hr\n" in detail and "stage=technical\n" in detail
    assert "evidence turn=visible-answer\n" in detail
    assert "segment=visible-segment" in detail
    assert "status=incomplete" in detail
    assert "Synthetic gap" in detail
    assert "assessment=pending" in detail and "score=pending coverage=pending" in detail

    assert cli.main(["results", "show", "--interview-id", seeded_cli["duplicate_id"]]) == 0
    failed = capsys.readouterr().out
    assert "assessment=failed_final" in failed
    assert "failure:" in failed
    assert "competencies=none" in failed
    assert "(no finalized transcript turns)" in failed


def test_results_output_neutralizes_terminal_control_sequences(
    seeded_cli: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["results", "list"]) == 0
    assert cli.main(["results", "show", "--interview-id", seeded_cli["interview_id"]]) == 0
    rendered = capsys.readouterr().out

    assert ESCAPE not in rendered
    assert "\x07" not in rendered
    assert "\\x1b[2J" in rendered
    assert "\\x1b]0;spoofed-title\\x07" in rendered
    # The visible characters of untrusted text are preserved; only the controls are escaped.
    assert "concrete answer" in rendered
    assert '<script>alert("candidate")</script>' in rendered
    # Every untrusted value stays on the line the renderer placed it on.
    assert all(
        line.startswith(
            (
                " ",
                "interview_id=",
                "candidate=",
                "state=",
                "created_at=",
                "note=",
                "stage=",
                "retained_interviews=",
            )
        )
        or not line
        for line in rendered.splitlines()
    )


def test_results_json_output_is_machine_readable_and_verbatim(
    seeded_cli: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["results", "list", "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert [item["interview_id"] for item in listing["interviews"]] == [
        seeded_cli["interview_id"],
        seeded_cli["duplicate_id"],
    ]
    assert listing["interviews"][0]["stages"][0]["average"] == 4.0
    assert listing["interviews"][0]["stages"][1]["assessment_state"] == "pending"

    assert (
        cli.main(["results", "show", "--interview-id", seeded_cli["interview_id"], "--json"]) == 0
    )
    detail = json.loads(capsys.readouterr().out)
    assert detail["candidate_name"] == MALICIOUS_NAME
    hr_stage = detail["stages"][0]
    technical_stage = detail["stages"][1]
    assert hr_stage["kind"] == "hr" and technical_stage["kind"] == "technical"
    assert hr_stage["transcript"][0]["text"] == MALICIOUS_TEXT
    assert hr_stage["assessment"]["assessed_count"] == 1
    assert hr_stage["assessment"]["competencies"][0]["evidence"][0]["turn_id"] == "visible-answer"
    assert hr_stage["assessment"]["competencies"][1]["score"] is None
    assert technical_stage["assessment"]["average"] is None
    recordings = {item["segment_id"]: item for item in hr_stage["recordings"]}
    assert recordings["visible-segment"]["manifest_failure"] == "Synthetic gap"


def test_recording_command_resolves_only_authorized_owned_files(
    seeded_cli: dict[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["results", "recording", "--segment-id", seeded_cli["segment_id"]]) == 0
    resolved = capsys.readouterr().out
    expected = tmp_path / "recordings" / "visible-recording" / "visible-segment.wav"
    assert f"path={expected}" in resolved
    assert "checksum_sha256=" in resolved

    assert cli.main(["results", "recording", "--segment-id", "traversal-segment"]) == 3
    assert "error=" in capsys.readouterr().err

    expected.unlink()
    assert cli.main(["results", "recording", "--segment-id", seeded_cli["segment_id"]]) == 3
    assert "unavailable" in capsys.readouterr().err


def test_unknown_and_expired_identifiers_report_not_found(
    seeded_cli: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_codes = [
        cli.main(["results", "show", "--interview-id", seeded_cli["expired_id"]]),
        cli.main(["results", "show", "--interview-id", "no-such-interview"]),
        cli.main(["results", "recording", "--segment-id", seeded_cli["expired_segment"]]),
        cli.main(["results", "recording", "--segment-id", "no-such-segment"]),
    ]
    captured = capsys.readouterr()

    assert exit_codes == [3, 3, 3, 3]
    assert captured.out == ""
    assert captured.err.count("error=") == 4


def test_results_subcommand_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as failure:
        cli.main(["results"])

    assert failure.value.code == 2
    assert "list" in capsys.readouterr().err
