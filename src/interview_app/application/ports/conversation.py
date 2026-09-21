"""Small control surface for a running conversational stage."""

from typing import Protocol


class StageConversation(Protocol):
    """Drive questions without exposing a provider session to application code."""

    async def ask_opening_question(self) -> None: ...

    async def wait_for_deadline(self, target_seconds: float) -> None:
        """Wait until the active deadline and allow an in-progress answer to finish."""
        ...
