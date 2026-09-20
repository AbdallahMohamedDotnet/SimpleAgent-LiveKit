import asyncio
import hashlib
import math
import struct
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

from interview_app.adapters.audio import WavRecordingSink
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecordingManifestStore,
    SqliteTranscriptStore,
)
from interview_app.application.ports.recording import RecordingWriteError
from interview_app.domain.models import (
    InterviewId,
    InterviewRecord,
    InterviewState,
    RecordingGap,
    RecordingStatus,
    Speaker,
    StageId,
    StageKind,
    StageRecord,
    StageState,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _interview() -> InterviewRecord:
    return InterviewRecord(
        id=InterviewId("interview-1"),
        candidate_name="Synthetic Candidate",
        state=InterviewState.CREATED,
        created_at=NOW,
    )


def _stage() -> StageRecord:
    return StageRecord(
        id=StageId("stage-1"),
        interview_id=InterviewId("interview-1"),
        kind=StageKind.HR,
        state=StageState.ACTIVE,
        created_at=NOW,
    )


def _tone(*, sample_rate_hz: int, seconds: float) -> bytes:
    frame_count = round(sample_rate_hz * seconds)
    samples = (
        round(4_000 * math.sin(2 * math.pi * 440 * index / sample_rate_hz))
        for index in range(frame_count)
    )
    return b"".join(struct.pack("<h", sample) for sample in samples)


def test_wav_manifest_is_playable_aligned_and_restartable(tmp_path: Path) -> None:
    async def exercise() -> None:
        sample_rate = 8_000
        database = SqliteDatabase(tmp_path / "recordings.sqlite3")
        await database.migrate()
        await SqliteInterviewStore(database).create(_interview())
        await SqliteTranscriptStore(database).create_stage(_stage())

        sink = WavRecordingSink(
            tmp_path / "audio",
            sample_rate_hz=sample_rate,
            queue_capacity=1,
        )
        await sink.start(InterviewId("interview-1"), started_at=NOW)
        await sink.start_segment(StageId("stage-1"), speaker=Speaker.CANDIDATE, offset_seconds=1.25)
        pcm = _tone(sample_rate_hz=sample_rate, seconds=0.25)
        await sink.write_pcm(pcm[:1000])
        await sink.write_pcm(pcm[1000:])
        gap = RecordingGap(offset_seconds=1.5, duration_seconds=0.1, reason="synthetic dropout")
        await sink.record_gap(gap)
        await sink.close_segment()
        manifest = await sink.close(completed_at=NOW + timedelta(seconds=2))

        assert manifest.status is RecordingStatus.INCOMPLETE
        assert len(manifest.segments) == 1
        segment = manifest.segments[0]
        assert segment.offset_seconds == 1.25
        assert segment.duration_seconds == 0.25
        assert segment.gaps == (gap,)
        wav_path = tmp_path / "audio" / segment.relative_path
        with wave.open(str(wav_path), "rb") as recording:
            assert recording.getframerate() == sample_rate
            assert recording.getnchannels() == 1
            assert recording.getsampwidth() == 2
            assert recording.getnframes() == sample_rate // 4
        assert segment.checksum_sha256 == hashlib.sha256(wav_path.read_bytes()).hexdigest()

        store = SqliteRecordingManifestStore(database)
        await store.save(manifest)
        await store.save(manifest)
        restarted = SqliteRecordingManifestStore(SqliteDatabase(tmp_path / "recordings.sqlite3"))
        assert await restarted.get(manifest.id) == manifest

    asyncio.run(exercise())


class _FailingWriter:
    def writeframesraw(self, data: bytes) -> None:
        del data
        raise OSError("synthetic disk full")

    def close(self) -> None:
        return None


def test_writer_failure_does_not_hang_and_remains_manifest_visible(tmp_path: Path) -> None:
    async def exercise() -> None:
        def failing_writer(path: Path, channels: int, width: int, rate: int) -> _FailingWriter:
            del path, channels, width, rate
            return _FailingWriter()

        sink = WavRecordingSink(
            tmp_path / "failed-audio",
            queue_capacity=1,
            writer_factory=failing_writer,
        )
        await sink.start(InterviewId("interview-1"), started_at=NOW)
        await sink.start_segment(StageId("stage-1"), speaker=Speaker.INTERVIEWER, offset_seconds=0)
        await sink.write_pcm(b"\x00\x00")
        try:
            await asyncio.wait_for(sink.close_segment(), timeout=1)
        except RecordingWriteError as error:
            assert "synthetic disk full" in str(error)
        else:
            raise AssertionError("A failed WAV writer must surface its disk error.")

        manifest = await sink.close(completed_at=NOW + timedelta(seconds=1))
        assert manifest.status is RecordingStatus.FAILED
        assert manifest.failure is not None
        assert "synthetic disk full" in manifest.failure
        assert len(manifest.segments) == 1
        assert manifest.segments[0].status is RecordingStatus.FAILED
        assert manifest.segments[0].checksum_sha256 == ""
        manifest_path = tmp_path / "failed-audio" / str(manifest.id) / "manifest.json"
        assert manifest_path.is_file()

    asyncio.run(exercise())
