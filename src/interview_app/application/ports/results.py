"""Read-only result-query boundary for local presentation adapters."""

from datetime import datetime
from typing import Protocol

from interview_app.application.results import InterviewResult, InterviewSummary, MediaRecord
from interview_app.domain.models import InterviewId, RecordingSegmentId


class ResultNotFoundError(LookupError):
    """Raised when a result is unknown, expired, or pending deletion."""


class ResultsReader(Protocol):
    async def list_interviews(self, *, now: datetime) -> tuple[InterviewSummary, ...]: ...

    async def get_interview(
        self,
        interview_id: InterviewId,
        *,
        now: datetime,
    ) -> InterviewResult: ...

    async def get_media(
        self,
        segment_id: RecordingSegmentId,
        *,
        now: datetime,
    ) -> MediaRecord: ...
