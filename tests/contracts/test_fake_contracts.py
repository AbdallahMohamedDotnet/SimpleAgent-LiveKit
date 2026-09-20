import asyncio

from interview_app.adapters.fakes import FakeClock, FakeStageRuntime, InMemoryInterviewStore
from interview_app.application.interview import DryRunInterview
from interview_app.application.ports.stage_runtime import StageLifecycleError
from interview_app.domain.models import InterviewState, StageEventType, StageKind


def test_dry_run_completes_two_ordered_stage_lifecycles() -> None:
    clock = FakeClock()
    store = InMemoryInterviewStore()
    use_case = DryRunInterview(
        clock=clock,
        store=store,
        runtimes={
            StageKind.HR: FakeStageRuntime(clock),
            StageKind.TECHNICAL: FakeStageRuntime(clock),
        },
    )

    result = asyncio.run(use_case.execute("  Ada Lovelace  "))

    assert result.interview.candidate_name == "Ada Lovelace"
    assert result.interview.state is InterviewState.INTERVIEW_FINISHED
    assert [(event.stage_kind, event.type) for event in result.events] == [
        (StageKind.HR, StageEventType.STARTED),
        (StageKind.HR, StageEventType.DRAINING),
        (StageKind.HR, StageEventType.CLOSED),
        (StageKind.TECHNICAL, StageEventType.STARTED),
        (StageKind.TECHNICAL, StageEventType.DRAINING),
        (StageKind.TECHNICAL, StageEventType.CLOSED),
    ]


def test_stage_runtime_requires_drain_before_close() -> None:
    async def exercise() -> None:
        clock = FakeClock()
        runtime = FakeStageRuntime(clock)
        store = InMemoryInterviewStore()
        use_case = DryRunInterview(
            clock=clock,
            store=store,
            runtimes={
                StageKind.HR: runtime,
                StageKind.TECHNICAL: FakeStageRuntime(clock),
            },
        )
        result = await use_case.execute("Grace Hopper")
        assert result.interview.state is InterviewState.INTERVIEW_FINISHED
        try:
            await runtime.close()
        except StageLifecycleError as error:
            assert "already closed" in str(error)
        else:
            raise AssertionError("Expected a second close to fail explicitly.")

    asyncio.run(exercise())
