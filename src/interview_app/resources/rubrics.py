"""Immutable rubric definitions consumed by interviewers and scoring workers."""

from interview_app.domain.rubrics import CompetencyRubric, StageRubric

HR_RUBRIC_V1 = StageRubric(
    version="hr-v1",
    competencies=(
        CompetencyRubric(
            "collaboration",
            "Works with others toward a job-related outcome.",
            "Gives no concrete actions or excludes others without explanation.",
            "Explains their role, how they involved others, trade-offs, and the observed outcome.",
        ),
        CompetencyRubric(
            "ownership",
            "Takes appropriate responsibility and follows work through.",
            "Provides only collective claims or shifts responsibility without concrete action.",
            "Identifies personal decisions, follow-through, course correction, and outcome.",
        ),
        CompetencyRubric(
            "feedback_reception",
            "Uses relevant feedback to improve work or reasoning.",
            "Cannot describe feedback received or any response to it.",
            "Explains the feedback, evaluation, action taken, and resulting change.",
        ),
        CompetencyRubric(
            "conflict_handling",
            "Handles job-related disagreement constructively.",
            "Describes blame or avoidance without an attempt to resolve the work issue.",
            "Clarifies perspectives, uses evidence, chooses a path, and reflects on the result.",
        ),
    ),
)


TECHNICAL_RUBRIC_V1 = StageRubric(
    version="technical-v1",
    competencies=(
        CompetencyRubric(
            "apis",
            "Designs and reasons about backend API contracts and failure behavior.",
            "Names API concepts without applying them to the case.",
            "Explains contracts, validation, idempotency, errors, and trade-offs in context.",
        ),
        CompetencyRubric(
            "databases",
            "Models data and reasons about consistency, queries, and transactions.",
            "Selects storage by vocabulary alone with no consistency or access reasoning.",
            "Connects access patterns and invariants to schema, indexes, and transaction choices.",
        ),
        CompetencyRubric(
            "debugging",
            "Investigates failures using hypotheses and observable evidence.",
            "Jumps to a fix without narrowing or validating the cause.",
            "Prioritizes hypotheses, measurements, isolation steps, and verification.",
        ),
        CompetencyRubric(
            "system_design",
            "Defines boundaries and reliability trade-offs for a backend system.",
            "Lists components without requirements, bottlenecks, or failure behavior.",
            "Uses requirements to justify boundaries, scaling, consistency, and recovery choices.",
        ),
        CompetencyRubric(
            "reasoning_and_decision_justification",
            "States assumptions and justifies decisions across technical cases.",
            "Offers conclusions without assumptions or trade-offs.",
            (
                "Makes assumptions explicit, compares alternatives, and identifies untested "
                "boundaries."
            ),
        ),
    ),
)
