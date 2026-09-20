# P07 — Durable background scoring and separate stage results

Implementation: **IN_PROGRESS**. Verification: **PARTIAL**. Updated 20 September 2026.

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P02 queue contracts; P05–P06 prompt/rubric contracts.

**Requirements covered:** R12–R15.

## Current state

The SQLite queue, leases, immutable snapshots, versioned HR/technical rubrics, and deterministic
assessment validator pass offline tests. Every numeric competency requires an exact span from a
candidate turn; unknown/interviewer/fabricated evidence and out-of-range scores are rejected.
Null competencies require a limitation, are excluded from the mean, and remain in coverage.
Durable result persistence, malformed-output parsing/retries, worker entrypoint, and the keyed
OpenRouter assessment call remain.

## Objective and scope

Replace the fake queue consumer with a reliable local scoring worker. HR scoring runs while the technical voice session continues. Assessors are ordinary LLM tasks, not additional voice sessions.

## Implementation tasks

1. Implement a separate worker entrypoint that claims persisted tasks using short atomic transactions and leases. Renew or recover leases after process failure.
2. Use the immutable stage snapshot, versioned rubric and a fresh assessment context. Call Sonnet 5 through OpenRouter; no STT/TTS or RoomIO is needed.
3. Require typed structured output for each expected competency: score 1–5 or null, assessment status, evidence spans, concise rationale and limitations. Technical results include difficulty and assistance.
4. Validate score ranges, complete unique competency keys, turn membership and exact evidence spans. Reject fabricated/mismatched evidence and unexpected fields that alter application behavior.
5. Use bounded same-model retries for malformed/transient failures. Record retryable/final failure clearly. Never manufacture a numeric score to satisfy the UI.
6. Calculate the stage average in deterministic application code over non-null competency scores with equal weights. A stage with no assessed competencies has a null average. Display coverage separately.
7. Keep HR and technical scores independent; do not create a combined score. A narrative summary may use Sonnet 5 but cannot change numeric results or block their display.
8. Complete results idempotently by stage/snapshot/rubric version. Prevent stale lease owners from overwriting newer results. A queue delivers at least once; result writes must tolerate repeats.
9. Avoid contention with voice calls. Bound scoring concurrency and give interactive work priority within shared provider limits. Scoring failure alone does not end the interview.
10. Calibrate rubric anchors with synthetic assessed transcripts. Test null handling, malformed JSON, invalid evidence, lease expiry, restart, duplicate delivery and delayed HR scoring during Technical.

## Deliverables

- Scoring worker, assessment port/provider adapter and output validators.
- Competency scores, evidence references, independent stage averages and task status.
- Calibration fixtures and queue/assessment integration evidence.

## Acceptance gate

- Slow HR scoring never blocks technical startup or ongoing conversation.
- Every numeric competency score has valid source evidence.
- Null is excluded from the mean, not converted to zero; no combined HR/technical score.
- Restart resumes pending work without duplicate final results or stale overwrites.
- A failed assessor is shown as failed/pending separately from conversation completion.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P07: Durable background scoring and separate stage results. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
