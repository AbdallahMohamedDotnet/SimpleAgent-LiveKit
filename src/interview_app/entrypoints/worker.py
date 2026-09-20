"""Long-running local scoring worker entrypoint support."""

import asyncio

from interview_app.adapters.clock import SystemClock
from interview_app.adapters.providers import OpenRouterAssessmentModel
from interview_app.adapters.sqlite import SqliteDatabase, SqliteScoreTaskStore
from interview_app.application.scoring import ScoreOneTask, ScoreWorkOutcome
from interview_app.resources.rubrics import HR_RUBRIC_V1, TECHNICAL_RUBRIC_V1
from interview_app.settings import ScoringSettings


async def run_worker(settings: ScoringSettings, *, once: bool) -> ScoreWorkOutcome | None:
    """Own the model client and process one task at a time to bound concurrency."""
    database = SqliteDatabase(settings.sqlite_path)
    await database.migrate()
    model = OpenRouterAssessmentModel(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
    )
    worker = ScoreOneTask(
        store=SqliteScoreTaskStore(database),
        model=model,
        rubrics={
            HR_RUBRIC_V1.version: HR_RUBRIC_V1,
            TECHNICAL_RUBRIC_V1.version: TECHNICAL_RUBRIC_V1,
        },
        clock=SystemClock(),
        worker_id=settings.worker_id,
    )
    try:
        while True:
            outcome = await worker.execute()
            if once:
                return outcome
            if outcome is None:
                await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        await model.aclose()
