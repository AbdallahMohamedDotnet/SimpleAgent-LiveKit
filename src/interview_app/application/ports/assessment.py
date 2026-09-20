"""Small provider boundary for non-voice transcript assessment."""

from typing import Protocol

from interview_app.domain.rubrics import StageRubric
from interview_app.domain.scoring import AssessmentTaskInput


class TransientAssessmentError(RuntimeError):
    """A bounded retry may succeed without changing configuration."""


class PermanentAssessmentError(RuntimeError):
    """Retrying the same request cannot succeed, such as an invalid key."""


class AssessmentModel(Protocol):
    @property
    def model_name(self) -> str: ...

    async def assess(self, task: AssessmentTaskInput, rubric: StageRubric) -> str:
        """Return one strict JSON assessment; never access voice or RoomIO."""
        ...
