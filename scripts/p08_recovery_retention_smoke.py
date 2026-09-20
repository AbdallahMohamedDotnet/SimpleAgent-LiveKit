"""Offline smoke test for P08 recovery and retention workflows."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from interview_app.adapters.artifacts import LocalArtifactStore
from interview_app.adapters.fakes import FakeClock
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecordingManifestStore,
    SqliteRecoveryStore,
    SqliteRetentionStore,
    SqliteTranscriptStore,
)
from interview_app.application.recovery import (
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


class RecoverOnSecondAttempt:
    def __init__(self) -> None:
        self.attempts = 0

    async def reconnect(self, checkpoint: RecoveryCheckpoint) -> ReconnectResult:
        self.attempts += 1
        if self.attempts == 1:
            raise TransientRecoveryError("synthetic local outage")
        return ReconnectResult(room_sid="RM_smoke_reconnected")


async def _run(root: Path) -> dict[str, object]:
    database = SqliteDatabase(root / "smoke.sqlite3")
    await database.migrate()
    interviews = SqliteInterviewStore(database)
    transcripts = SqliteTranscriptStore(database)

    recovery_id = InterviewId("p08-recovery")
    recovery_stage_id = StageId("p08-recovery-stage")
    question_id = TurnId("p08-cut-off-question")
    await interviews.create(
        InterviewRecord(
            id=recovery_id,
            candidate_name="Synthetic Recovery Candidate",
            state=InterviewState.HR_ACTIVE,
            created_at=NOW,
            room_name="p08-smoke-room",
            room_sid="RM_smoke_original",
            candidate_identity="p08-smoke-candidate",
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=recovery_stage_id,
            interview_id=recovery_id,
            kind=StageKind.HR,
            state=StageState.ACTIVE,
            created_at=NOW,
        )
    )
    await transcripts.append_turn(
        TurnRecord(
            id=question_id,
            stage_id=recovery_stage_id,
            speaker=Speaker.INTERVIEWER,
            text="Describe a disagreement you resolved.",
            is_final=True,
            delivery_status=DeliveryStatus.UNCERTAIN,
            occurred_at=NOW,
        )
    )
    checkpoint = RecoveryCheckpoint(
        interview_id=recovery_id,
        stage_id=recovery_stage_id,
        stage_kind=StageKind.HR,
        resumable_state=InterviewState.HR_ACTIVE,
        remaining_active_seconds=201.0,
        last_committed_turn_id=question_id,
        last_committed_event_id=None,
        interrupted_question_turn_id=question_id,
        room_name="p08-smoke-room",
        room_sid="RM_smoke_original",
        candidate_identity="p08-smoke-candidate",
        active_recording_segment_id=None,
        recovery_started_at=None,
        recovery_deadline_at=None,
        recovery_attempts=0,
        updated_at=NOW,
    )
    clock = FakeClock(now=NOW)

    async def advance(seconds: float) -> None:
        clock.advance(seconds)

    recovered = await RecoverInterview(
        store=SqliteRecoveryStore(database),
        clock=clock,
        reconnector=RecoverOnSecondAttempt(),
        sleep=advance,
    ).execute(checkpoint)

    expired_id = InterviewId("p08-expired")
    expired_stage_id = StageId("p08-expired-stage")
    expired_at = NOW - timedelta(days=30)
    await interviews.create(
        InterviewRecord(
            id=expired_id,
            candidate_name="Synthetic Expired Candidate",
            state=InterviewState.INTERVIEW_FINISHED,
            created_at=expired_at,
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=expired_stage_id,
            interview_id=expired_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=expired_at,
        )
    )
    recording_id = RecordingId("p08-expired-recording")
    segment_id = RecordingSegmentId("p08-expired-segment")
    recording_directory = root / "recordings" / str(recording_id)
    recording_directory.mkdir(parents=True)
    relative_audio = f"{recording_id}/{segment_id}.wav"
    (recording_directory / f"{segment_id}.wav").write_bytes(b"RIFF smoke")
    (recording_directory / "manifest.json").write_text("{}", encoding="utf-8")
    await SqliteRecordingManifestStore(database).save(
        RecordingManifest(
            id=recording_id,
            interview_id=expired_id,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            started_at=expired_at,
            completed_at=expired_at + timedelta(minutes=1),
            status=RecordingStatus.COMPLETE,
            failure=None,
            segments=(
                RecordingSegment(
                    id=segment_id,
                    recording_id=recording_id,
                    stage_id=expired_stage_id,
                    speaker=Speaker.CANDIDATE,
                    relative_path=relative_audio,
                    offset_seconds=0,
                    duration_seconds=1,
                    checksum_sha256="smoke",
                    status=RecordingStatus.COMPLETE,
                    gaps=(),
                ),
            ),
        )
    )
    cleanup = await CleanupExpiredInterviews(
        store=SqliteRetentionStore(database),
        artifacts=LocalArtifactStore(root / "recordings"),
        clock=FakeClock(now=NOW),
    ).execute()

    return {
        "status": "passed",
        "recovery": {
            "resumed": recovered.resumed,
            "attempts": recovered.checkpoint.recovery_attempts,
            "stage": recovered.checkpoint.stage_kind.value,
            "remaining_active_seconds": recovered.checkpoint.remaining_active_seconds,
            "room_sid_changed": recovered.checkpoint.room_sid == "RM_smoke_reconnected",
            "reask_turn_id": recovered.reask_question_turn_id,
        },
        "retention": {
            "prepared": cleanup.prepared,
            "deleted": list(cleanup.deleted),
            "failed": list(cleanup.failed),
            "recording_removed": not recording_directory.exists(),
        },
        "provider_request_made": False,
    }


def main() -> None:
    with TemporaryDirectory(prefix="p08-smoke-") as temporary_directory:
        result = asyncio.run(_run(Path(temporary_directory)))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
