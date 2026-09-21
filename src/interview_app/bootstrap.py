"""Composition root for constructing application use cases."""

from interview_app.adapters.clock import SystemClock
from interview_app.adapters.fakes import FakeClock, FakeStageRuntime, InMemoryInterviewStore
from interview_app.adapters.livekit import LiveKitInterviewLaunchGateway
from interview_app.adapters.sqlite import SqliteDatabase, SqliteInterviewStore, SqliteResultsReader
from interview_app.adapters.web import ControlHttpApplication, ResultsHttpApplication
from interview_app.application.interview import DryRunInterview
from interview_app.application.launch import GetInterviewMission, StartInterview
from interview_app.domain.models import StageKind
from interview_app.settings import ControlSettings, ResultsSettings


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


def build_control_application(
    settings: ControlSettings,
) -> tuple[SqliteDatabase, ControlHttpApplication]:
    """Construct the localhost operator console and LiveKit launch boundary."""
    database = SqliteDatabase(settings.sqlite_path)
    interviews = SqliteInterviewStore(database)
    evidence = SqliteResultsReader(database)
    gateway = LiveKitInterviewLaunchGateway(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        agent_name=settings.agent_name,
    )
    return database, ControlHttpApplication(
        start_interview=StartInterview(
            clock=SystemClock(),
            interviews=interviews,
            gateway=gateway,
        ),
        get_mission=GetInterviewMission(
            clock=SystemClock(),
            interviews=interviews,
            gateway=gateway,
            evidence=evidence,
        ),
    )
