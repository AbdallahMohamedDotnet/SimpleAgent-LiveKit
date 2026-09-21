import asyncio
from datetime import datetime
from urllib.parse import urlencode

from interview_app.adapters.fakes import FakeClock, InMemoryInterviewStore
from interview_app.adapters.web import ControlHttpApplication
from interview_app.application.launch import GetInterviewMission, StartInterview
from interview_app.application.ports.interview_launch import (
    LaunchBinding,
    LaunchRequest,
    LaunchStatus,
)
from interview_app.application.results import InterviewResult, ResultTurn, StageResult
from interview_app.domain.models import (
    DeliveryStatus,
    InterviewId,
    InterviewState,
    Speaker,
    StageId,
    StageKind,
    StageState,
    TurnId,
)


class ConsoleEvidenceReader:
    def __init__(self, *, include_turn: bool = False) -> None:
        self._include_turn = include_turn

    async def get_interview(
        self,
        interview_id: InterviewId,
        *,
        now: datetime,
    ) -> InterviewResult:
        turns = (
            (
                ResultTurn(
                    id=TurnId("turn-console"),
                    speaker=Speaker.CANDIDATE,
                    text='<img src=x onerror="alert(1)">',
                    delivery_status=DeliveryStatus.DELIVERED,
                    occurred_at=now,
                ),
            )
            if self._include_turn
            else ()
        )
        stages = (
            StageResult(
                id=StageId("stage-console"),
                kind=StageKind.HR,
                state=StageState.ACTIVE,
                turns=turns,
                assessment=None,
                recordings=(),
            ),
        )
        return InterviewResult(
            id=interview_id,
            candidate_name="Candidate",
            state=InterviewState.HR_ACTIVE,
            created_at=now,
            stages=stages,
        )


class ConsoleGateway:
    def __init__(self) -> None:
        self.requests: list[LaunchRequest] = []

    async def launch(self, request: LaunchRequest) -> LaunchBinding:
        self.requests.append(request)
        return LaunchBinding(room_sid="RM_console", dispatch_id="dispatch-console")

    async def get_status(
        self,
        *,
        room_name: str,
        candidate_identity: str,
    ) -> LaunchStatus:
        return LaunchStatus(
            room_available=True,
            dispatch_created=True,
            agent_joined=True,
            candidate_joined=False,
        )

    async def cancel(self, room_name: str) -> None:
        return


def test_control_console_launches_and_renders_escaped_status() -> None:
    async def exercise() -> None:
        store = InMemoryInterviewStore()
        gateway = ConsoleGateway()
        application = ControlHttpApplication(
            start_interview=StartInterview(
                clock=FakeClock(),
                interviews=store,
                gateway=gateway,
            ),
            get_mission=GetInterviewMission(
                clock=FakeClock(),
                interviews=store,
                gateway=gateway,
                evidence=ConsoleEvidenceReader(include_turn=True),
            ),
            csrf_token="known-token",
        )

        form = await application.handle("GET", "/interviews/new")
        assert form.status == 200
        assert b"Start a voice interview" in form.body
        assert b'class="mic-icon"' in form.body
        assert b"known-token" in form.body
        assert form.headers["Content-Security-Policy"].find("form-action 'self'") >= 0

        interviews_root = await application.handle("GET", "/interviews/")
        assert interviews_root.status == 303
        assert interviews_root.headers["Location"] == "/interviews/new"

        payload = urlencode(
            {"csrf_token": "known-token", "candidate_name": '<script>alert("x")</script>'}
        ).encode()
        started = await application.handle(
            "POST",
            "/interviews",
            body=payload,
            content_type="application/x-www-form-urlencoded",
        )
        assert started.status == 303
        location = started.headers["Location"]
        assert location.startswith("/interviews/")
        assert gateway.requests

        status = await application.handle("GET", location)
        assert status.status == 200
        assert b"&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in status.body
        assert b'<script>alert("x")</script>' not in status.body
        assert b"Interview agent" in status.body
        assert b"Joined" in status.body
        assert b"Candidate audio" in status.body
        assert b"Not connected" in status.body
        assert b"Microphone not connected" in status.body
        assert b"interview join" in status.body
        assert status.headers["Refresh"] == "2"
        assert b"Interview transcript" in status.body
        assert b"&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in status.body
        assert b'<img src=x onerror="alert(1)">' not in status.body

    asyncio.run(exercise())


def test_control_console_rejects_cross_site_or_duplicate_launch() -> None:
    async def exercise() -> None:
        store = InMemoryInterviewStore()
        gateway = ConsoleGateway()
        application = ControlHttpApplication(
            start_interview=StartInterview(clock=FakeClock(), interviews=store, gateway=gateway),
            get_mission=GetInterviewMission(
                clock=FakeClock(),
                interviews=store,
                gateway=gateway,
                evidence=ConsoleEvidenceReader(),
            ),
            csrf_token="known-token",
        )
        rejected = await application.handle(
            "POST",
            "/interviews",
            body=urlencode({"csrf_token": "wrong", "candidate_name": "Candidate"}).encode(),
            content_type="application/x-www-form-urlencoded",
        )
        assert rejected.status == 403
        assert not gateway.requests

        first = urlencode(
            {"csrf_token": "known-token", "candidate_name": "First Candidate"}
        ).encode()
        second = urlencode(
            {"csrf_token": "known-token", "candidate_name": "Second Candidate"}
        ).encode()
        assert (
            await application.handle(
                "POST",
                "/interviews",
                body=first,
                content_type="application/x-www-form-urlencoded",
            )
        ).status == 303
        conflict = await application.handle(
            "POST",
            "/interviews",
            body=second,
            content_type="application/x-www-form-urlencoded",
        )
        assert conflict.status == 409

    asyncio.run(exercise())
