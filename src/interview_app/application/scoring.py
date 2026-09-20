"""Lease-safe background assessment orchestration."""

from dataclasses import dataclass
from datetime import timedelta

from interview_app.application.ports.assessment import (
    AssessmentModel,
    PermanentAssessmentError,
    TransientAssessmentError,
)
from interview_app.application.ports.clock import Clock
from interview_app.application.ports.score_task_store import ScoreTaskStore
from interview_app.domain.models import ScoreTaskRecord, ScoreTaskState
from interview_app.domain.rubrics import StageRubric
from interview_app.domain.scoring import (
    AssessmentValidationError,
    StageScoreRecord,
    parse_assessment_json,
    validate_stage_assessment,
)


@dataclass(frozen=True, slots=True)
class ScoreWorkOutcome:
    task_state: ScoreTaskState
    result: StageScoreRecord | None


class ScoreOneTask:
    """Claim and assess one task; provider work occurs outside database transactions."""

    def __init__(
        self,
        *,
        store: ScoreTaskStore,
        model: AssessmentModel,
        rubrics: dict[str, StageRubric],
        clock: Clock,
        worker_id: str,
        lease_duration: timedelta = timedelta(minutes=5),
        retry_delay: timedelta = timedelta(seconds=15),
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive.")
        self._store = store
        self._model = model
        self._rubrics = dict(rubrics)
        self._clock = clock
        self._worker_id = worker_id
        self._lease_duration = lease_duration
        self._retry_delay = retry_delay
        self._max_attempts = max_attempts

    async def execute(self) -> ScoreWorkOutcome | None:
        task = await self._store.claim_next(
            worker_id=self._worker_id,
            now=self._clock.utc_now(),
            lease_duration=self._lease_duration,
        )
        if task is None:
            return None
        task_input = await self._store.load_input(task.id)
        rubric = self._rubrics.get(task.rubric_version)
        if rubric is None:
            failed = await self._store.fail(
                task.id,
                worker_id=self._worker_id,
                failed_at=self._clock.utc_now(),
                failure=f"Unknown rubric version: {task.rubric_version}",
                retry_at=None,
            )
            return ScoreWorkOutcome(task_state=failed.state, result=None)

        try:
            raw_output = await self._model.assess(task_input, rubric)
            parsed = parse_assessment_json(raw_output)
            assessment = validate_stage_assessment(
                rubric=rubric,
                turns=task_input.turns,
                assessments=parsed.competencies,
            )
        except PermanentAssessmentError as error:
            return await self._record_failure(task, str(error), retryable=False)
        except (TransientAssessmentError, AssessmentValidationError) as error:
            return await self._record_failure(task, str(error), retryable=True)

        result = await self._store.complete_with_result(
            task.id,
            worker_id=self._worker_id,
            completed_at=self._clock.utc_now(),
            model=self._model.model_name,
            assessment=assessment,
            summary=parsed.summary,
        )
        return ScoreWorkOutcome(task_state=ScoreTaskState.SUCCEEDED, result=result)

    async def _record_failure(
        self, task: ScoreTaskRecord, failure: str, *, retryable: bool
    ) -> ScoreWorkOutcome:
        retry_at = (
            self._clock.utc_now() + self._retry_delay
            if retryable and task.attempts < self._max_attempts
            else None
        )
        failed = await self._store.fail(
            task.id,
            worker_id=self._worker_id,
            failed_at=self._clock.utc_now(),
            failure=failure,
            retry_at=retry_at,
        )
        return ScoreWorkOutcome(task_state=failed.state, result=None)
