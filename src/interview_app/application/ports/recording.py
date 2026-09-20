"""Job-scoped recording and durable manifest contracts."""

from datetime import datetime
from typing import Protocol

from interview_app.domain.models import (
    InterviewId,
    RecordingGap,
    RecordingId,
    RecordingManifest,
    Speaker,
    StageId,
)


class RecordingLifecycleError(RuntimeError):
    """Raised when recorder lifecycle ordering or media format is invalid."""


class RecordingWriteError(RuntimeError):
    """Raised when queued media cannot be written durably."""


class RecordingSink(Protocol):
    """Own recording files for a job, independently of stage runtimes.

    PCM writes are bounded by adapter backpressure. Closing a segment does not
    close the job recorder, allowing it to survive a stage handoff.
    """

    async def start(self, interview_id: InterviewId, *, started_at: datetime) -> None: ...

    async def start_segment(
        self,
        stage_id: StageId,
        *,
        speaker: Speaker,
        offset_seconds: float,
    ) -> None: ...

    async def write_pcm(self, frames: bytes) -> None: ...

    async def record_gap(self, gap: RecordingGap) -> None: ...

    async def close_segment(self) -> None: ...

    async def close(self, *, completed_at: datetime) -> RecordingManifest: ...


class RecordingManifestStore(Protocol):
    async def save(self, manifest: RecordingManifest) -> None: ...

    async def get(self, recording_id: RecordingId) -> RecordingManifest: ...
