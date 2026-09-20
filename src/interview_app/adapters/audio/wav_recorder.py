"""Bounded, job-scoped PCM WAV recorder for observable media."""

from __future__ import annotations

import asyncio
import hashlib
import json
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from interview_app.application.ports.recording import (
    RecordingLifecycleError,
    RecordingWriteError,
)
from interview_app.domain.models import (
    InterviewId,
    RecordingGap,
    RecordingId,
    RecordingManifest,
    RecordingSegment,
    RecordingSegmentId,
    RecordingStatus,
    Speaker,
    StageId,
)


class _WaveWriter(Protocol):
    def writeframesraw(self, data: bytes) -> None: ...

    def close(self) -> None: ...


type _WriterFactory = Callable[[Path, int, int, int], _WaveWriter]


@dataclass(slots=True)
class _OpenSegment:
    id: RecordingSegmentId
    stage_id: StageId
    speaker: Speaker
    relative_path: str
    absolute_path: Path
    offset_seconds: float
    writer: _WaveWriter
    frames_written: int = 0
    gaps: list[RecordingGap] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Frames:
    data: bytes


class WavRecordingSink:
    """Write one observable PCM track at a time without blocking the event loop."""

    def __init__(
        self,
        data_root: Path,
        *,
        sample_rate_hz: int = 16_000,
        channels: int = 1,
        sample_width_bytes: int = 2,
        queue_capacity: int = 64,
        writer_factory: _WriterFactory | None = None,
    ) -> None:
        if sample_rate_hz <= 0 or channels <= 0 or sample_width_bytes <= 0:
            raise ValueError("Audio format values must be positive.")
        if queue_capacity <= 0:
            raise ValueError("queue_capacity must be positive.")
        self._data_root = data_root.resolve()
        self._sample_rate_hz = sample_rate_hz
        self._channels = channels
        self._sample_width_bytes = sample_width_bytes
        self._queue_capacity = queue_capacity
        self._writer_factory = writer_factory or self._open_writer
        self._recording_id: RecordingId | None = None
        self._interview_id: InterviewId | None = None
        self._started_at: datetime | None = None
        self._segment: _OpenSegment | None = None
        self._segments: list[RecordingSegment] = []
        self._failure: str | None = None
        self._closed = False
        self._queue: asyncio.Queue[_Frames | None] | None = None
        self._writer_task: asyncio.Task[None] | None = None

    async def start(self, interview_id: InterviewId, *, started_at: datetime) -> None:
        if self._recording_id is not None:
            raise RecordingLifecycleError("Recorder may only be started once.")
        self._require_aware(started_at)
        recording_id = RecordingId(str(uuid4()))
        directory = self._resolve_owned(str(recording_id))
        try:
            await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=False)
        except OSError as error:
            message = f"Recording directory creation failed: {type(error).__name__}: {error}"
            raise RecordingWriteError(message) from error
        self._recording_id = recording_id
        self._interview_id = interview_id
        self._started_at = started_at

    async def start_segment(
        self,
        stage_id: StageId,
        *,
        speaker: Speaker,
        offset_seconds: float,
    ) -> None:
        self._require_active()
        if self._segment is not None:
            raise RecordingLifecycleError("Close the active segment before starting another.")
        if offset_seconds < 0:
            raise ValueError("offset_seconds must not be negative.")
        segment_id = RecordingSegmentId(str(uuid4()))
        relative_path = f"{self._recording_id}/{segment_id}.wav"
        absolute_path = self._resolve_owned(relative_path)
        try:
            writer = await asyncio.to_thread(
                self._writer_factory,
                absolute_path,
                self._channels,
                self._sample_width_bytes,
                self._sample_rate_hz,
            )
        except OSError as error:
            self._failure = f"WAV open failed: {type(error).__name__}: {error}"
            raise RecordingWriteError(self._failure) from error
        self._segment = _OpenSegment(
            id=segment_id,
            stage_id=stage_id,
            speaker=speaker,
            relative_path=relative_path,
            absolute_path=absolute_path,
            offset_seconds=offset_seconds,
            writer=writer,
        )
        self._queue = asyncio.Queue(maxsize=self._queue_capacity)
        self._writer_task = asyncio.create_task(
            self._write_loop(self._segment, self._queue),
            name=f"recording-{segment_id}",
        )

    async def write_pcm(self, frames: bytes) -> None:
        self._raise_writer_failure()
        if not frames:
            return
        frame_size = self._channels * self._sample_width_bytes
        if len(frames) % frame_size:
            raise RecordingLifecycleError("PCM data must contain complete audio frames.")
        if self._queue is None or self._segment is None:
            raise RecordingLifecycleError("No recording segment is active.")
        await self._enqueue(_Frames(bytes(frames)))
        self._raise_writer_failure()

    async def record_gap(self, gap: RecordingGap) -> None:
        if gap.offset_seconds < 0 or gap.duration_seconds <= 0 or not gap.reason.strip():
            raise ValueError("A recording gap needs non-negative offset, duration, and reason.")
        if self._segment is None:
            raise RecordingLifecycleError("No recording segment is active.")
        self._segment.gaps.append(gap)

    async def close_segment(self) -> None:
        if self._segment is None or self._queue is None or self._writer_task is None:
            raise RecordingLifecycleError("No recording segment is active.")
        segment = self._segment
        failure: RecordingWriteError | None = None
        cancellation: asyncio.CancelledError | None = None
        try:
            await self._enqueue(None)
            await self._writer_task
        except asyncio.CancelledError as error:
            cancellation = error
            self._writer_task.cancel()
            await asyncio.gather(self._writer_task, return_exceptions=True)
            self._failure = "Recording segment close was cancelled."
        except RecordingWriteError as error:
            failure = error
            self._failure = str(error)
        except Exception as error:
            self._failure = f"WAV write failed: {type(error).__name__}: {error}"
            failure = RecordingWriteError(self._failure)
        finally:
            try:
                await asyncio.to_thread(segment.writer.close)
            except Exception as error:
                self._failure = f"WAV close failed: {type(error).__name__}: {error}"
                failure = RecordingWriteError(self._failure)
        duration = segment.frames_written / self._sample_rate_hz
        status = RecordingStatus.COMPLETE
        if self._failure is not None:
            status = RecordingStatus.FAILED
        elif segment.gaps:
            status = RecordingStatus.INCOMPLETE
        checksum = ""
        if segment.absolute_path.is_file():
            checksum = await asyncio.to_thread(self._sha256_file, segment.absolute_path)
        self._segments.append(
            RecordingSegment(
                id=segment.id,
                recording_id=self._recording_id_or_raise(),
                stage_id=segment.stage_id,
                speaker=segment.speaker,
                relative_path=segment.relative_path,
                offset_seconds=segment.offset_seconds,
                duration_seconds=duration,
                checksum_sha256=checksum,
                status=status,
                gaps=tuple(segment.gaps),
            )
        )
        self._segment = None
        self._queue = None
        self._writer_task = None
        if failure is not None:
            raise failure
        if cancellation is not None:
            raise cancellation

    async def close(self, *, completed_at: datetime) -> RecordingManifest:
        self._require_active()
        self._require_aware(completed_at)
        if self._segment is not None:
            try:
                await self.close_segment()
            except RecordingWriteError:
                pass
        if self._closed:
            raise RecordingLifecycleError("Recorder is already closed.")
        status = RecordingStatus.COMPLETE
        if self._failure is not None:
            status = RecordingStatus.FAILED
        elif any(segment.status is not RecordingStatus.COMPLETE for segment in self._segments):
            status = RecordingStatus.INCOMPLETE
        manifest = RecordingManifest(
            id=self._recording_id_or_raise(),
            interview_id=self._interview_id_or_raise(),
            sample_rate_hz=self._sample_rate_hz,
            channels=self._channels,
            sample_width_bytes=self._sample_width_bytes,
            started_at=self._started_at_or_raise(),
            completed_at=completed_at,
            status=status,
            failure=self._failure,
            segments=tuple(self._segments),
        )
        try:
            await asyncio.to_thread(self._write_manifest, manifest)
        except OSError as error:
            self._failure = f"Manifest write failed: {type(error).__name__}: {error}"
            raise RecordingWriteError(self._failure) from error
        self._closed = True
        return manifest

    async def _write_loop(
        self,
        segment: _OpenSegment,
        queue: asyncio.Queue[_Frames | None],
    ) -> None:
        while True:
            command = await queue.get()
            try:
                if command is None:
                    return
                await asyncio.to_thread(segment.writer.writeframesraw, command.data)
                segment.frames_written += len(command.data) // (
                    self._channels * self._sample_width_bytes
                )
            finally:
                queue.task_done()

    async def _enqueue(self, command: _Frames | None) -> None:
        if self._queue is None or self._writer_task is None:
            raise RecordingLifecycleError("No recording segment is active.")
        put_task = asyncio.create_task(self._queue.put(command))
        done, _ = await asyncio.wait(
            {put_task, self._writer_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if self._writer_task in done:
            if not put_task.done():
                put_task.cancel()
                await asyncio.gather(put_task, return_exceptions=True)
            self._raise_writer_failure()
            raise RecordingWriteError("WAV writer stopped before accepting queued media.")
        await put_task

    def _write_manifest(self, manifest: RecordingManifest) -> None:
        path = self._recording_directory() / "manifest.json"
        temporary = path.with_suffix(".tmp")
        payload = {
            "id": manifest.id,
            "interview_id": manifest.interview_id,
            "sample_rate_hz": manifest.sample_rate_hz,
            "channels": manifest.channels,
            "sample_width_bytes": manifest.sample_width_bytes,
            "started_at": manifest.started_at.isoformat(),
            "completed_at": manifest.completed_at.isoformat(),
            "status": manifest.status.value,
            "failure": manifest.failure,
            "segments": [
                {
                    "id": segment.id,
                    "stage_id": segment.stage_id,
                    "speaker": segment.speaker.value,
                    "relative_path": segment.relative_path,
                    "offset_seconds": segment.offset_seconds,
                    "duration_seconds": segment.duration_seconds,
                    "checksum_sha256": segment.checksum_sha256,
                    "status": segment.status.value,
                    "gaps": [
                        {
                            "offset_seconds": gap.offset_seconds,
                            "duration_seconds": gap.duration_seconds,
                            "reason": gap.reason,
                        }
                        for gap in segment.gaps
                    ],
                }
                for segment in manifest.segments
            ],
        }
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _raise_writer_failure(self) -> None:
        if self._writer_task is not None and self._writer_task.done():
            error = self._writer_task.exception()
            if error is not None:
                self._failure = f"WAV write failed: {type(error).__name__}: {error}"
                raise RecordingWriteError(self._failure) from error

    @staticmethod
    def _sha256_file(path: Path) -> str:
        checksum = hashlib.sha256()
        with path.open("rb") as audio_file:
            for block in iter(lambda: audio_file.read(64 * 1024), b""):
                checksum.update(block)
        return checksum.hexdigest()

    def _recording_directory(self) -> Path:
        return self._resolve_owned(str(self._recording_id_or_raise()))

    def _resolve_owned(self, relative_path: str) -> Path:
        candidate = (self._data_root / relative_path).resolve()
        if not candidate.is_relative_to(self._data_root):
            raise RecordingLifecycleError("Recording path escaped the owned data root.")
        return candidate

    def _require_active(self) -> None:
        if self._recording_id is None or self._closed:
            raise RecordingLifecycleError("Recorder is not active.")

    def _recording_id_or_raise(self) -> RecordingId:
        if self._recording_id is None:
            raise RecordingLifecycleError("Recorder has not started.")
        return self._recording_id

    def _interview_id_or_raise(self) -> InterviewId:
        if self._interview_id is None:
            raise RecordingLifecycleError("Recorder has not started.")
        return self._interview_id

    def _started_at_or_raise(self) -> datetime:
        if self._started_at is None:
            raise RecordingLifecycleError("Recorder has not started.")
        return self._started_at

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Recording timestamps must be timezone-aware.")

    @staticmethod
    def _open_writer(
        path: Path,
        channels: int,
        sample_width_bytes: int,
        sample_rate_hz: int,
    ) -> _WaveWriter:
        writer = wave.open(str(path), "wb")
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width_bytes)
        writer.setframerate(sample_rate_hz)
        return writer
