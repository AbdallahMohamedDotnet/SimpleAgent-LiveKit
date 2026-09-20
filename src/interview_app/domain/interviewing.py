"""Evidence-oriented interview policies independent of voice and model SDKs."""

from dataclasses import dataclass
from enum import StrEnum


class HrCompetency(StrEnum):
    COLLABORATION = "collaboration"
    OWNERSHIP = "ownership"
    FEEDBACK = "feedback_reception"
    CONFLICT = "conflict_handling"


class TechnicalCompetency(StrEnum):
    APIS = "apis"
    DATABASES = "databases"
    DEBUGGING = "debugging"
    SYSTEM_DESIGN = "system_design"
    REASONING = "reasoning_and_decision_justification"


class Difficulty(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class AnswerEvidence(StrEnum):
    SOUND_WITH_JUSTIFICATION = "sound_with_justification"
    PARTIAL = "partial"
    STUCK = "stuck"
    OFF_TOPIC = "off_topic"


@dataclass(frozen=True, slots=True)
class DifficultyDecision:
    next_difficulty: Difficulty
    ask_clarification: bool
    offer_hint: bool
    reason: str


class TechnicalDifficultyPolicy:
    """Adapt only from answer evidence, never confidence, voice, or fluency."""

    def decide(
        self,
        *,
        current: Difficulty,
        evidence: AnswerEvidence,
        hint_already_used: bool,
    ) -> DifficultyDecision:
        if evidence is AnswerEvidence.SOUND_WITH_JUSTIFICATION:
            next_difficulty = {
                Difficulty.JUNIOR: Difficulty.MID,
                Difficulty.MID: Difficulty.SENIOR,
                Difficulty.SENIOR: Difficulty.SENIOR,
            }[current]
            return DifficultyDecision(
                next_difficulty=next_difficulty,
                ask_clarification=False,
                offer_hint=False,
                reason="The prior answer was sound and justified with observable trade-offs.",
            )
        if evidence is AnswerEvidence.PARTIAL:
            return DifficultyDecision(
                next_difficulty=current,
                ask_clarification=True,
                offer_hint=False,
                reason=(
                    "The answer contained relevant evidence but needs one concise clarification."
                ),
            )
        if evidence is AnswerEvidence.STUCK:
            return DifficultyDecision(
                next_difficulty=current,
                ask_clarification=False,
                offer_hint=not hint_already_used,
                reason=(
                    "The candidate is stuck; one small recorded hint may reveal the next boundary."
                ),
            )
        return DifficultyDecision(
            next_difficulty=current,
            ask_clarification=True,
            offer_hint=False,
            reason="The answer did not address the case, so difficulty must not increase.",
        )
