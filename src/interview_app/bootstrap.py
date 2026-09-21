"""Composition root for constructing application use cases."""

from pathlib import Path

from interview_app.adapters.artifacts import LocalRecordingLocator
from interview_app.adapters.clock import SystemClock
from interview_app.adapters.fakes import FakeClock, FakeStageRuntime, InMemoryInterviewStore
from interview_app.adapters.livekit import LiveKitInterviewLaunchGateway
from interview_app.adapters.sqlite import (
    SqliteDatabase,
    SqliteInterviewStore,
    SqliteRecoveryStore,
    SqliteResultsReader,
)
from interview_app.application.interview import DryRunInterview
from interview_app.application.launch import GetInterviewMission, StartInterview
from interview_app.application.recovery import ReconcileInterruptedInterviews
from interview_app.domain.models import StageKind
from interview_app.settings import LaunchSettings, ResultsSettings


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


def build_results_reader(
    settings: ResultsSettings,
) -> tuple[SqliteDatabase, SqliteResultsReader, LocalRecordingLocator]:
    """Construct the read-only results projection and its owned recording locator."""
    database = SqliteDatabase(settings.sqlite_path)
    return (
        database,
        SqliteResultsReader(database),
        LocalRecordingLocator(settings.recordings_root),
    )


def build_interruption_reconciler(
    sqlite_path: Path,
) -> tuple[SqliteDatabase, ReconcileInterruptedInterviews]:
    """Construct the startup pass that closes interviews whose job process no longer exists."""
    database = SqliteDatabase(sqlite_path)
    return database, ReconcileInterruptedInterviews(
        store=SqliteRecoveryStore(database),
        clock=SystemClock(),
    )


def build_start_interview(settings: LaunchSettings) -> tuple[SqliteDatabase, StartInterview]:
    """Construct the room/dispatch allocation use case for the terminal candidate client."""
    database = SqliteDatabase(settings.sqlite_path)
    return database, StartInterview(
        clock=SystemClock(),
        interviews=SqliteInterviewStore(database),
        gateway=launch_gateway(settings),
    )


def build_get_mission(settings: LaunchSettings) -> tuple[SqliteDatabase, GetInterviewMission]:
    """Construct the read-only room, dispatch and transcript status query."""
    database = SqliteDatabase(settings.sqlite_path)
    return database, GetInterviewMission(
        clock=SystemClock(),
        interviews=SqliteInterviewStore(database),
        gateway=launch_gateway(settings),
        evidence=SqliteResultsReader(database),
    )


def launch_gateway(settings: LaunchSettings) -> LiveKitInterviewLaunchGateway:
    return LiveKitInterviewLaunchGateway(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        agent_name=settings.agent_name,
    )
