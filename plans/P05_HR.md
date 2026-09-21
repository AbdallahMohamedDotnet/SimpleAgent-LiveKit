# P05 — HR behavioral interview

Current status is tracked only in [PROGRESS.md](../PROGRESS.md).

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P04.

**Requirements covered:** R05, R07–R10, R13–R14.

## Current state

A thin HR Agent, versioned English instructions, four-competency rubric, neutral evidence rules,
and prompt-scope tests are implemented. The instructions require actual work situations, actions,
and outcomes; reject candidate instruction injection; and prohibit grammar, accent, personality,
mental-health, and hiring-decision inferences. OpenRouter generated and persisted one opening HR
question from live STT input. A complete behavioral stage, validated completion tools,
competency/turn tagging, and synthetic strong/weak/vague conversations remain.

## Objective and scope

Create an HR interviewer focused on real work situations and four job-related competencies. The role is behavioral assessment, not psychological diagnosis.

## Implementation tasks

1. Create versioned English HR instructions and a separate rubric resource for collaboration, ownership, feedback reception and conflict handling.
2. Ask for an actual situation, the candidate's role, their actions and the outcome. Use concise follow-ups for missing evidence; do not require a fictional scenario or a specific experience the candidate never had.
3. Generate questions dynamically. Use one question at a time and adapt to provided evidence while respecting the timer.
4. Expose only small validated tools, such as recording a question/competency reference or requesting stage completion. The application controller retains authority over time and lifecycle.
5. Associate all questions, candidate answers and follow-ups with immutable turn IDs. Distinguish candidate claims from independently verified facts.
6. Do not evaluate accent, grammar, inferred emotions or mental health. Do not ask irrelevant personal questions or issue a hire/reject decision.
7. Do not force all four competencies into five minutes. Mark uncovered or insufficiently evidenced areas for null assessment.
8. Finish through the P03 handoff protocol. No HR score is required before transfer.
9. Test synthetic strong, weak, vague and insufficient-evidence conversations, including an answer that attempts to alter system instructions.

## Deliverables

- HR Agent adapter and versioned prompts/rubric.
- Four competency definitions with observable anchors and examples.
- Synthetic HR scenarios and evidence-oriented tests.

## Acceptance gate

- Questions concern actual situations and elicit actions/outcomes.
- Behavior remains within four job-related competencies; no personality diagnosis.
- English quality does not affect assessment input policy.
- HR snapshot is complete and available to the technical stage even when scoring remains pending.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P05: HR behavioral interview. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
