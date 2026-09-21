# P06 — Adaptive Staff Engineer interview

Current status is tracked only in [PROGRESS.md](../PROGRESS.md).

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P04–P05.

**Requirements covered:** R06–R10, R13–R14.

## Current state

A thin technical Agent, versioned five-competency rubric, injection-safe attributed HR evidence
rendering, and deterministic difficulty policy are implemented. Tests prove Junior-first
progression, advancement only after sound justified evidence, clarification for partial/off-topic
answers, and at most one small hint when stuck. Generated-case/hint persistence, live adaptive
questioning, difficulty-boundary storage, and provider verification remain.

## Objective and scope

Generate different general-backend cases, start at Junior difficulty and probe demonstrated boundaries within five minutes. Reasoning is assessed across cases, not as an extra timed stage.

## Implementation tasks

1. Create versioned Staff Engineer instructions and rubrics for APIs, databases, debugging, system design and reasoning/problem-solving/decision justification.
2. Load HR Q/A as attributed reference data. Use relevant project context to personalize cases, but do not count an HR self-description as technical performance evidence.
3. Begin with a fundamentals-level case. After a sound answer with justification, increase the next case's complexity. For partial answers, ask a concise clarification; for a stuck candidate, allow a small recorded hint.
4. Use different cases, not a single mandatory expanding scenario. Maintain competency/difficulty tags and reasons for adapting difficulty.
5. Record each hint and separate independent performance from assisted performance. Do not automatically subtract a fixed point for requesting help.
6. Ask for assumptions, debugging steps and trade-offs. Correct vocabulary alone is insufficient evidence of deeper reasoning.
7. Generate questions dynamically within the selected domains and rubric. Do not add a fixed question bank or a coding editor requirement.
8. Respect P04 timing. Uncovered competencies remain unassessed; no forced coverage at the cost of truncating an answer.
9. Save the highest independently demonstrated complexity, assisted complexity and untested boundaries. Do not declare a definitive Senior level from this short screen.
10. Test weak, strong, assisted, off-topic and HR prompt-injection scenarios. Ensure the initial difficulty does not increase merely because the candidate sounds confident.

## Deliverables

- Technical Agent adapter, generated-case records and versioned prompts/rubrics.
- Explicit difficulty-transition policy and hint events.
- Synthetic scenarios demonstrating adaptive behavior and evidence boundaries.

## Acceptance gate

- Starts at Junior-level fundamentals; uses different cases where time permits.
- Difficulty progression is explainable from answers, not voice or fluency.
- HR answers are available without importing HR instructions/scores.
- Hints and observed independent/assisted boundaries appear in persisted evidence.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P06: Adaptive Staff Engineer interview. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
