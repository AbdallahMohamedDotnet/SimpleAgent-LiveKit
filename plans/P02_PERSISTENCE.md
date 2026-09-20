# P02 — SQLite, evidence persistence and recording

Implementation: **IN_PROGRESS**. Verification: **PARTIAL**. Updated 20 September 2026.

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P01; P00 audio findings for real recorder integration.

**Requirements covered:** R03, R13, R15.

## Current state

Three idempotent SQLite migrations now cover interviews, stages, turns, immutable snapshots,
lease-based score tasks, recording manifests/segments, and handoff events. WAL, foreign keys,
busy timeout, restart persistence, conflicting duplicate rejection, atomic snapshot/task enqueue,
lease reclamation, bounded asynchronous PCM-to-WAV writing, checksums, gaps, and restartable
manifests pass offline tests. Checksums cover the actual WAV artifact; writer/directory/manifest
errors are classified, queue backpressure cannot hang after writer failure, cancellation performs
bounded cleanup, and failed segments remain visible in a failed manifest. Identical durable stage,
turn, and event deliveries are idempotent while conflicting reuse is rejected. The fake score
consumer obeys the same task lease contract. Actual observable LiveKit media capture and
real-device timestamp alignment remain blocked by P00, so P02 is not marked implemented or passed.

## Latest continuation note — 20 September 2026

The SQLite duplicate-stage path was repaired so an identical repeated stage record is idempotent,
while reuse of the same stage ID with changed evidence raises `EvidenceConflictError`. Regression
coverage was added for both cases. The focused P02 SQLite/recording tests passed (4 tests), Ruff
formatting and lint passed, strict mypy passed for 28 source files, and the full pytest suite passed
(15 tests). P02 remains **IN_PROGRESS / PARTIAL** because observable LiveKit candidate/agent media
capture and real-device timestamp alignment cannot be verified in the current environment:
`/dev/snd`, provider credentials, LiveKit credentials, and both voice IDs are absent. All currently
identified offline P02 work passes.

## Objective and scope

Build durable interview evidence and task storage before orchestration depends on it. Audio recording is an adapter with explicit lifecycle and gaps, not a side effect of a prompt.

## Implementation tasks

1. Implement versioned migrations and the schema in ARCHITECTURE.md, introducing tables as they gain consumers. Configure foreign keys, WAL and a busy timeout.
2. Implement consumer-oriented repositories and short transactions. Keep SQL in SQLite adapters and use validated typed records at application boundaries.
3. Persist final turns during conversation with idempotent event IDs. Preserve interim/final distinction and delivery uncertainty; do not grade a transient partial STT hypothesis.
4. Finalize an immutable transcript snapshot and enqueue a unique assessment task in the same transaction. Store snapshot hash, rubric version and stage ID.
5. Implement task claim/lease/complete contracts and a fake consumer so P03 can prove background work before P07's real scorer exists.
6. Generate internal IDs for interviews, stages and participants. Candidate names may repeat and never become paths or SQL fragments.
7. Implement a job-scoped recorder using the P00-verified capture route. Keep aligned candidate/agent tracks or segments, stage boundary markers, discontinuities and checksums/status.
8. Capture observable media rather than assuming every generated TTS sample reached the candidate. Preserve uncertain delivery; do not fabricate missing frames.
9. Use bounded audio queues and safe offloading for encoding/disk writes. Handle disk errors explicitly. Keep recorder lifecycle independent of stage cleanup.
10. Add contract tests for migrations, duplicate events, snapshot atomicity, short concurrent writes, worker lease expiry and recording manifests.

## Deliverables

- SQLite migrations/adapters and shared repository contracts.
- Immutable snapshots, durable score tasks, recording files/manifests and restartable reads.
- Synthetic database/audio fixtures without real candidate information.

## Acceptance gate

- Restart preserves finalized turns and queue tasks.
- Duplicate delivery cannot create duplicate turns or final scores.
- Concurrent controller/worker/viewer access does not hold a database lock across network work.
- Audio is playable with aligned timestamps; recording failures are visible and gaps remain explicit.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P02: SQLite, evidence persistence and recording. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
