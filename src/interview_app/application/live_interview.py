"""Application orchestration for a complete two-stage live interview."""

from collections.abc import Mapping

from interview_app.application.handoff import (
    HandoffResult,
    InterviewCompletion,
    TwoStageHandoffController,
)
from interview_app.application.ports.conversation import StageConversation
from interview_app.domain.models import InterviewRecord, StageKind


class LiveInterviewCoordinator:
    """Run sequential sessions while scoring remains an independent durable task."""

    def __init__(
        self,
        *,
        controller: TwoStageHandoffController,
        conversations: Mapping[StageKind, StageConversation],
        hr_target_seconds: float,
        technical_target_seconds: float,
    ) -> None:
        self._controller = controller
        self._conversations = conversations
        self._hr_target_seconds = hr_target_seconds
        self._technical_target_seconds = technical_target_seconds

    async def execute(
        self, interview: InterviewRecord
    ) -> tuple[HandoffResult, InterviewCompletion]:
        await self._controller.begin(interview)
        await self._conversations[StageKind.HR].ask_opening_question()
        await self._conversations[StageKind.HR].wait_for_deadline(self._hr_target_seconds)
        handoff = await self._controller.handoff(interview.id)
        await self._conversations[StageKind.TECHNICAL].ask_opening_question()
        await self._conversations[StageKind.TECHNICAL].wait_for_deadline(
            self._technical_target_seconds
        )
        completion = await self._controller.finish(interview.id)
        return handoff, completion
