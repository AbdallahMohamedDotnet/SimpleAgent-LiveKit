import asyncio
from datetime import datetime

from interview_app.adapters.fakes import FakeClock, InMemoryInterviewStore
from interview_app.application.interview import InvalidCandidateNameError
from interview_app.application.launch import GetInterviewMission, StartInterview
from interview_app.application.ports.interview_launch import (
    LaunchBinding,
    LaunchRequest,
    LaunchStatus,
)
from interview_app.application.ports.interview_store import InterviewStateConflictError
from interview_app.application.results import InterviewResult
from interview_app.domain.models import InterviewId, InterviewState


class EmptyEvidenceReader:
    async def get_interview(
        self,
        interview_id: InterviewId,
        *,
        now: datetime,
    ) -> InterviewResult:
        return InterviewResult(
            id=interview_id,
            candidate_name="Candidate Name",
            state=InterviewState.CREATED,
            created_at=now,
            stages=(),
        )


class FakeLaunchGateway:
    def __init__(self) -> None:
        self.requests: list[LaunchRequest] = []
        self.cancelled: list[str] = []
        self.status = LaunchStatus(True, True, True, False)

    async def launch(self, request: LaunchRequest) -> LaunchBinding:
        self.requests.append(request)
        return LaunchBinding(room_sid=f"RM_{len(self.requests)}", dispatch_id="dispatch-1")

    async def get_status(
        self,
        *,
        room_name: str,
        candidate_identity: str,
    ) -> LaunchStatus:
        assert room_name.startswith("interview-")
        assert candidate_identity.startswith("candidate-")
        return self.status

    async def cancel(self, room_name: str) -> None:
        self.cancelled.append(room_name)


def test_start_interview_generates_bindings_and_exposes_mission_status() -> None:
    async def exercise() -> None:
        gateway = FakeLaunchGateway()
        store = InMemoryInterviewStore()
        start = StartInterview(clock=FakeClock(), interviews=store, gateway=gateway)

        result = await start.execute("  Candidate Name  ")
        mission = await GetInterviewMission(
            clock=FakeClock(),
            interviews=store,
            gateway=gateway,
            evidence=EmptyEvidenceReader(),
        ).execute(result.interview.id)

        assert result.interview.candidate_name == "Candidate Name"
        assert result.interview.room_sid == "RM_1"
        assert result.interview.room_name == gateway.requests[0].room_name
        assert result.interview.candidate_identity == gateway.requests[0].candidate_identity
        assert result.dispatch_id == "dispatch-1"
        assert mission.status.agent_joined is True
        assert mission.status.candidate_joined is False
        assert mission.transcript == ()

    asyncio.run(exercise())


def test_start_interview_rejects_bad_names_and_cancels_room_on_store_conflict() -> None:
    async def exercise() -> None:
        gateway = FakeLaunchGateway()
        store = InMemoryInterviewStore()
        start = StartInterview(clock=FakeClock(), interviews=store, gateway=gateway)

        for name in ("", " " * 3, "x" * 121):
            try:
                await start.execute(name)
            except InvalidCandidateNameError:
                pass
            else:
                raise AssertionError("An invalid candidate name was accepted.")
        assert not gateway.requests

        await start.execute("First candidate")
        try:
            await start.execute("Second candidate")
        except InterviewStateConflictError:
            pass
        else:
            raise AssertionError("A second active interview was accepted.")
        assert gateway.cancelled == [gateway.requests[-1].room_name]

    asyncio.run(exercise())
