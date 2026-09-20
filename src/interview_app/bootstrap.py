"""Composition root for constructing application use cases."""

from interview_app.adapters.fakes import FakeClock, FakeStageRuntime, InMemoryInterviewStore
from interview_app.application.interview import DryRunInterview
from interview_app.domain.models import StageKind


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
