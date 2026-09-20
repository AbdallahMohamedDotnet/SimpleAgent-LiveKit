import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from interview_app.adapters.fakes import FakeClock
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteScoreTaskStore,
    SqliteTranscriptStore,
)
from interview_app.application.ports.assessment import PermanentAssessmentError
from interview_app.application.scoring import ScoreOneTask
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
    ScoreTaskState,
    Speaker,
    StageId,
    StageKind,
    StageRecord,
    StageState,
    TurnId,
    TurnRecord,
)
from interview_app.domain.rubrics import StageRubric
from interview_app.domain.scoring import AssessmentTaskInput
from interview_app.resources.rubrics import HR_RUBRIC_V1

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


class ScriptedAssessmentModel:
    def __init__(self, outputs: list[str | Exception]) -> None:
        self._outputs = outputs

    @property
    def model_name(self) -> str:
        return "test/sonnet-5"

    async def assess(self, task: AssessmentTaskInput, rubric: StageRubric) -> str:
        assert task.stage_kind is StageKind.HR
        assert rubric is HR_RUBRIC_V1
        output = self._outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def _valid_output() -> str:
    return json.dumps(
        {
            "competencies": [
                {
                    "competency": "collaboration",
                    "status": "assessed",
                    "score": 4,
                    "rationale": "The candidate involved peers and recorded the decision.",
                    "evidence": [
                        {
                            "turn_id": "candidate-answer",
                            "quote": "asked two peers to review",
                        }
                    ],
                    "limitation": None,
                },
                *[
                    {
                        "competency": key,
                        "status": "insufficient_evidence",
                        "score": None,
                        "rationale": "This competency was not covered.",
                        "evidence": [],
                        "limitation": "No relevant final candidate answer was captured.",
                    }
                    for key in (
                        "ownership",
                        "feedback_reception",
                        "conflict_handling",
                    )
                ],
            ],
            "summary": "Evidence is limited to one collaboration example.",
        }
    )


async def _enqueue(database: SqliteDatabase) -> None:
    await database.migrate()
    interviews = SqliteInterviewStore(database)
    transcripts = SqliteTranscriptStore(database)
    await interviews.create(
        InterviewRecord(
            id=InterviewId("interview-score"),
            candidate_name="Candidate",
            state=InterviewState.HR_ACTIVE,
            created_at=NOW,
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=StageId("stage-score"),
            interview_id=InterviewId("interview-score"),
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=NOW,
        )
    )
    await transcripts.append_turn(
        TurnRecord(
            id=TurnId("candidate-answer"),
            stage_id=StageId("stage-score"),
            speaker=Speaker.CANDIDATE,
            text="I asked two peers to review the options and recorded our decision.",
            is_final=True,
            delivery_status=DeliveryStatus.DELIVERED,
            occurred_at=NOW + timedelta(seconds=1),
        )
    )
    await transcripts.finalize_snapshot_and_enqueue(
        StageId("stage-score"), rubric_version=HR_RUBRIC_V1.version, created_at=NOW
    )


def test_worker_retries_malformed_output_then_persists_one_result_after_restart(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        path = tmp_path / "scoring.sqlite3"
        database = SqliteDatabase(path)
        await _enqueue(database)
        clock = FakeClock(now=NOW)
        first_store = SqliteScoreTaskStore(database)
        first_worker = ScoreOneTask(
            store=first_store,
            model=ScriptedAssessmentModel(["not-json"]),
            rubrics={HR_RUBRIC_V1.version: HR_RUBRIC_V1},
            clock=clock,
            worker_id="worker-1",
        )

        first = await first_worker.execute()
        assert first is not None
        assert first.task_state is ScoreTaskState.FAILED_RETRYABLE
        assert first.result is None
        assert await first_worker.execute() is None

        clock.advance(15)
        restarted_database = SqliteDatabase(path)
        await restarted_database.migrate()
        restarted_store = SqliteScoreTaskStore(restarted_database)
        second_worker = ScoreOneTask(
            store=restarted_store,
            model=ScriptedAssessmentModel([_valid_output()]),
            rubrics={HR_RUBRIC_V1.version: HR_RUBRIC_V1},
            clock=clock,
            worker_id="worker-2",
        )
        second = await second_worker.execute()

        assert second is not None
        assert second.task_state is ScoreTaskState.SUCCEEDED
        assert second.result is not None
        assert second.result.assessment.average == 4.0
        assert second.result.assessment.assessed_count == 1
        assert second.result.assessment.total_count == 4
        assert second.result.assessment.competencies[0].evidence[0].turn_id == TurnId(
            "candidate-answer"
        )
        assert await restarted_store.get_result(second.result.task_id) == second.result
        assert await second_worker.execute() is None

    asyncio.run(exercise())


def test_permanent_assessor_failure_is_final_without_ending_conversation(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = SqliteDatabase(tmp_path / "failure.sqlite3")
        await _enqueue(database)
        clock = FakeClock(now=NOW)
        store = SqliteScoreTaskStore(database)
        worker = ScoreOneTask(
            store=store,
            model=ScriptedAssessmentModel([PermanentAssessmentError("invalid provider key")]),
            rubrics={HR_RUBRIC_V1.version: HR_RUBRIC_V1},
            clock=clock,
            worker_id="worker-final",
        )

        outcome = await worker.execute()

        assert outcome is not None
        assert outcome.task_state is ScoreTaskState.FAILED_FINAL
        assert outcome.result is None
        interview = await SqliteInterviewStore(database).get(InterviewId("interview-score"))
        assert interview.state is InterviewState.HR_ACTIVE
        assert await worker.execute() is None

    asyncio.run(exercise())
