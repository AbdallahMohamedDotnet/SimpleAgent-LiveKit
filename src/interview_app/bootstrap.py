"""Composition root for constructing application use cases."""

from interview_app.adapters.clock import SystemClock
from interview_app.adapters.fakes import FakeClock, FakeStageRuntime, InMemoryInterviewStore
from interview_app.adapters.sqlite import SqliteDatabase, SqliteResultsReader
from interview_app.adapters.web import ResultsHttpApplication
from interview_app.application.interview import DryRunInterview
from interview_app.domain.models import StageKind
from interview_app.settings import ResultsSettings


def build_dry_run_interview() -> DryRunInterview:
    """Build an entirely offline lifecycle; no SDK or environment access occurs."""
    clock = FakeClock()
    return DryRunInterview(
        clock=clock,
        store=InMemoryInterviewStore(),
        runtimes={
            StageKind.HR: FakeStageRuntime(clock),
            StageKind.TECHNICAL: FakeStageRuntime(clock),
        },
    )


def build_results_application(
    settings: ResultsSettings,
) -> tuple[SqliteDatabase, ResultsHttpApplication]:
    """Construct the read-only results projection and presentation adapter."""
    database = SqliteDatabase(settings.sqlite_path)
    return database, ResultsHttpApplication(
        reader=SqliteResultsReader(database),
        recordings_root=settings.recordings_root,
        clock=SystemClock(),
    )
