"""Offline end-to-end smoke test for the P09 read-only terminal results commands."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecordingManifestStore,
    SqliteTranscriptStore,
)
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
    Speaker,
    StageId,
    StageKind,
    StageRecord,
    StageState,
    TurnId,
    TurnRecord,
)
from interview_app.entrypoints import cli

INJECTED_NAME = "Smoke \x1b[2J\x1b[1;31mcandidate"
INJECTED_TEXT = "Evidence \x1b]0;spoofed\x07"


async def _seed(database: SqliteDatabase, recordings_root: Path) -> None:
    now = datetime.now(UTC)
    await database.migrate()
    interview_id = InterviewId("p09-smoke-interview")
    stage_id = StageId("p09-smoke-hr")
    await SqliteInterviewStore(database).create(
        InterviewRecord(
            id=interview_id,
            candidate_name=INJECTED_NAME,
            state=InterviewState.INCOMPLETE,
            created_at=now,
        )
    )
    transcripts = SqliteTranscriptStore(database)
    await transcripts.create_stage(
        StageRecord(
            id=stage_id,
            interview_id=interview_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=now,
        )
    )
    await transcripts.append_turn(
        TurnRecord(
            id=TurnId("p09-smoke-turn"),
            stage_id=stage_id,
            speaker=Speaker.CANDIDATE,
            text=INJECTED_TEXT,
            is_final=True,
            delivery_status=DeliveryStatus.DELIVERED,
            occurred_at=now,
        )
    )
    media = b"RIFF-p09-smoke-wave"
    relative_path = "p09-smoke-recording/candidate.wav"
    path = recordings_root / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(media)
    await SqliteRecordingManifestStore(database).save(
        RecordingManifest(
            id=RecordingId("p09-smoke-recording"),
            interview_id=interview_id,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            started_at=now,
            completed_at=now,
            status=RecordingStatus.COMPLETE,
            failure=None,
            segments=(
                RecordingSegment(
                    id=RecordingSegmentId("p09-smoke-segment"),
                    recording_id=RecordingId("p09-smoke-recording"),
                    stage_id=stage_id,
                    speaker=Speaker.CANDIDATE,
                    relative_path=relative_path,
                    offset_seconds=0,
                    duration_seconds=1,
                    checksum_sha256=hashlib.sha256(media).hexdigest(),
                    status=RecordingStatus.COMPLETE,
                    gaps=(),
                ),
            ),
        )
    )


def _run(*arguments: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(arguments))
    return code, out.getvalue(), err.getvalue()


def main() -> None:
    with TemporaryDirectory(prefix="p09-results-smoke-") as temporary_directory:
        root = Path(temporary_directory)
        recordings_root = root / "recordings"
        sqlite_path = root / "interviews.sqlite3"
        asyncio.run(_seed(SqliteDatabase(sqlite_path), recordings_root))
        previous_directory = Path.cwd()
        os.environ["SQLITE_PATH"] = str(sqlite_path)
        os.environ["RECORDINGS_DIR"] = str(recordings_root)
        # Run from the temporary directory so the repository .env is not read.
        os.chdir(root)
        try:
            list_exit, listing, _ = _run("results", "list")
            show_exit, detail, _ = _run("results", "show", "--interview-id", "p09-smoke-interview")
            json_exit, detail_json, _ = _run(
                "results", "show", "--interview-id", "p09-smoke-interview", "--json"
            )
            recording_exit, recording, _ = _run(
                "results", "recording", "--segment-id", "p09-smoke-segment"
            )
            missing_exit, missing_out, missing_err = _run(
                "results", "recording", "--segment-id", "no-such-segment"
            )
        finally:
            os.chdir(previous_directory)
        decoded = json.loads(detail_json)
        resolved_path = Path(
            next(
                line.removeprefix("path=")
                for line in recording.splitlines()
                if line.startswith("path=")
            )
        )
        recording_inside_owned_root = resolved_path.is_relative_to(recordings_root.resolve())

    checks = {
        "list_exit": list_exit,
        "show_exit": show_exit,
        "json_exit": json_exit,
        "recording_exit": recording_exit,
        "missing_exit": missing_exit,
        "control_sequences_escaped": "\x1b" not in listing + detail + recording
        and "\\x1b[2J" in listing,
        "json_keeps_text_verbatim": decoded["stages"][0]["transcript"][0]["text"] == INJECTED_TEXT,
        "recording_inside_owned_root": recording_inside_owned_root,
        "missing_reported_on_stderr": missing_out == "" and "error=" in missing_err,
        "provider_request_made": False,
    }
    expected = {
        "list_exit": 0,
        "show_exit": 0,
        "json_exit": 0,
        "recording_exit": 0,
        "missing_exit": 3,
        "control_sequences_escaped": True,
        "json_keeps_text_verbatim": True,
        "recording_inside_owned_root": True,
        "missing_reported_on_stderr": True,
        "provider_request_made": False,
    }
    if checks != expected:
        raise RuntimeError(f"P09 smoke checks failed: {checks}")
    print(json.dumps({"status": "passed", **checks}, indent=2))


if __name__ == "__main__":
    main()
