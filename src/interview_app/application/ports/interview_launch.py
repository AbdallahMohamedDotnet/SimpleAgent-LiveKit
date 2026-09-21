"""Infrastructure contract for creating and observing a LiveKit interview mission."""

from dataclasses import dataclass
from typing import Protocol

from interview_app.domain.models import InterviewId


class InterviewLaunchError(RuntimeError):
    """Raised when the local room or agent dispatch cannot be managed."""


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    interview_id: InterviewId
    room_name: str
    candidate_identity: str


@dataclass(frozen=True, slots=True)
class LaunchBinding:
    room_sid: str
    dispatch_id: str


@dataclass(frozen=True, slots=True)
class LaunchStatus:
    room_available: bool
    dispatch_created: bool
    agent_joined: bool
    candidate_joined: bool


class InterviewLaunchGateway(Protocol):
    """Create one room/dispatch and compensate failed persistence safely."""

    async def launch(self, request: LaunchRequest) -> LaunchBinding: ...

    async def get_status(
        self,
        *,
        room_name: str,
        candidate_identity: str,
    ) -> LaunchStatus: ...

    async def cancel(self, room_name: str) -> None: ...
