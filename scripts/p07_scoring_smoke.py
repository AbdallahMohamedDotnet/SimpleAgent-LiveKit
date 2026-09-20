"""Offline smoke test for the durable P07 scoring worker.

This test uses the production SQLite repositories and scoring use case with a
deterministic local assessment model. It makes no provider or LiveKit request.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from interview_app.adapters.fakes import FakeClock
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteScoreTaskStore,
    SqliteTranscriptStore,
)
from interview_app.application.scoring import ScoreOneTask
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewRecord,
    InterviewState,
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

STARTED_AT = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


class SmokeAssessmentModel:
    @property
    def model_name(self) -> str:
        return "offline/smoke-assessor"

    async def assess(self, task: AssessmentTaskInput, rubric: StageRubric) -> str:
        if task.stage_kind is not StageKind.HR or rubric.version != HR_RUBRIC_V1.version:
            raise RuntimeError("Smoke task was routed to the wrong rubric.")
        return json.dumps(
            {
                "competencies": [
                    {
                        "competency": "collaboration",
                        "status": "assessed",
                        "score": 4,
                        "rationale": "The answer gives a concrete collaborative action.",
                        "evidence": [
                            {
                                "turn_id": "smoke-answer",
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
                            "rationale": "The smoke transcript does not cover this competency.",
                            "evidence": [],
                            "limitation": "No relevant final candidate evidence was captured.",
                        }
                        for key in (
                            "ownership",
                            "feedback_reception",
                            "conflict_handling",
                        )
                    ],
                ],
                "summary": "One competency has direct evidence; three remain unassessed.",
            }
        )


async def _run(database_path: Path) -> dict[str, object]:
    database = SqliteDatabase(database_path)
    await database.migrate()
    interviews = SqliteInterviewStore(database)
    transcripts = SqliteTranscriptStore(database)
    tasks = SqliteScoreTaskStore(database)

    interview_id = InterviewId("p07-smoke-interview")
    stage_id = StageId("p07-smoke-stage")
    await interviews.create(
        InterviewRecord(
            id=interview_id,
            candidate_name="Synthetic Smoke Candidate",
            state=InterviewState.INTERVIEW_FINISHED,
            created_at=STARTED_AT,
        )
    )
    await transcripts.create_stage(
        StageRecord(
            id=stage_id,
            interview_id=interview_id,
            kind=StageKind.HR,
            state=StageState.CLOSED,
            created_at=STARTED_AT,
        )
    )
    await transcripts.append_turn(
        TurnRecord(
            id=TurnId("smoke-answer"),
            stage_id=stage_id,
            speaker=Speaker.CANDIDATE,
            text="I asked two peers to review the options before documenting the decision.",
            is_final=True,
            delivery_status=DeliveryStatus.DELIVERED,
            occurred_at=STARTED_AT,
        )
    )
    _, queued_task = await transcripts.finalize_snapshot_and_enqueue(
        stage_id,
        rubric_version=HR_RUBRIC_V1.version,
        created_at=STARTED_AT,
    )

    worker = ScoreOneTask(
        store=tasks,
        model=SmokeAssessmentModel(),
        rubrics={HR_RUBRIC_V1.version: HR_RUBRIC_V1},
        clock=FakeClock(now=STARTED_AT),
        worker_id="p07-smoke-worker",
    )
    outcome = await worker.execute()
    if outcome is None or outcome.result is None:
        raise RuntimeError("Smoke worker did not persist a result.")

    restarted_store = SqliteScoreTaskStore(SqliteDatabase(database_path))
    restarted_result = await restarted_store.get_result(queued_task.id)
    if restarted_result != outcome.result:
        raise RuntimeError("Persisted score did not survive repository restart.")
    if await worker.execute() is not None:
        raise RuntimeError("A succeeded task was delivered more than once.")

    return {
        "status": "passed",
        "task_id": queued_task.id,
        "task_state": outcome.task_state.value,
        "stage": StageKind.HR.value,
        "average": restarted_result.assessment.average,
        "coverage": {
            "assessed": restarted_result.assessment.assessed_count,
            "total": restarted_result.assessment.total_count,
        },
        "restart_read_verified": True,
        "provider_request_made": False,
    }


def main() -> None:
    with TemporaryDirectory(prefix="p07-scoring-smoke-") as temporary_directory:
        result = asyncio.run(_run(Path(temporary_directory) / "smoke.sqlite3"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
