"""Thin LiveKit Agent subclasses for the versioned interview roles."""

from livekit.agents import Agent

from interview_app.domain.models import HandoffPayload
from interview_app.resources.prompts import HR_INSTRUCTIONS_V1, technical_instructions_with_handoff


class HrInterviewerAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=HR_INSTRUCTIONS_V1)


class TechnicalInterviewerAgent(Agent):
    def __init__(self, handoff: HandoffPayload) -> None:
        super().__init__(instructions=technical_instructions_with_handoff(handoff))
