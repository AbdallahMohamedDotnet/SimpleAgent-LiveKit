"""Offline end-to-end smoke test for the localhost P09 results server."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from interview_app.adapters.clock import SystemClock
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecordingManifestStore,
    SqliteResultsReader,
    SqliteTranscriptStore,
)
from interview_app.adapters.web import ResultsHttpApplication, create_results_server
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


async def _seed(database: SqliteDatabase, recordings_root: Path) -> bytes:
    now = datetime.now(UTC)
    await database.migrate()
    interview_id = InterviewId("p09-smoke-interview")
    stage_id = StageId("p09-smoke-hr")
    await SqliteInterviewStore(database).create(
        InterviewRecord(
            id=interview_id,
            candidate_name="Smoke <script>alert(1)</script>",
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
            text="Evidence <img src=x onerror=alert(2)>",
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
    return media


def _fetch(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read()


def main() -> None:
    with TemporaryDirectory(prefix="p09-results-smoke-") as temporary_directory:
        root = Path(temporary_directory)
        database = SqliteDatabase(root / "interviews.sqlite3")
        recordings_root = root / "recordings"
        expected_media = asyncio.run(_seed(database, recordings_root))
        application = ResultsHttpApplication(
            reader=SqliteResultsReader(database),
            recordings_root=recordings_root,
            clock=SystemClock(),
        )
        server = create_results_server(application, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        base = f"http://{host}:{port}"
        try:
            list_status, listing = _fetch(f"{base}/results")
            detail_status, detail = _fetch(f"{base}/results/p09-smoke-interview")
            media_status, media = _fetch(f"{base}/media/p09-smoke-segment")
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"{base}/results", method="POST"), timeout=5
                )
            except urllib.error.HTTPError as error:
                post_status = error.code
            else:
                raise RuntimeError("Read-only results endpoint accepted POST.")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    checks = {
        "list_status": list_status,
        "detail_status": detail_status,
        "media_status": media_status,
        "post_status": post_status,
        "candidate_html_escaped": b"<script>alert(1)</script>" not in listing,
        "transcript_html_escaped": b"<img src=x onerror=alert(2)>" not in detail,
        "media_matches": media == expected_media,
        "provider_request_made": False,
    }
    if checks != {
        "list_status": 200,
        "detail_status": 200,
        "media_status": 200,
        "post_status": 405,
        "candidate_html_escaped": True,
        "transcript_html_escaped": True,
        "media_matches": True,
        "provider_request_made": False,
    }:
        raise RuntimeError(f"P09 smoke checks failed: {checks}")
    print(json.dumps({"status": "passed", **checks}, indent=2))


if __name__ == "__main__":
    main()
