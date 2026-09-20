# P08 — Recovery, restart and 30-day retention

Implementation: **IN_PROGRESS**. Verification: **PARTIAL**. Updated 20 September 2026.

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** P03–P07.

**Requirements covered:** R15, R16, R18.

## Current state

The active-stage timer excludes recovery, task leases can be reclaimed, retries share one fixed
120-second monotonic recovery budget, and a pure retention policy expires data exactly 30 UTC days
after interview start. Checkpoint persistence, failure classification/retry orchestration, startup
reconciliation, expiry-aware reads, deletion workflow, cleanup command, and scheduler
documentation remain.

## Objective and scope

Make transient outages recoverable and retained data expire predictably. Preserve exact boundaries between live reconnect, process restart and server-room loss.

## Implementation tasks

1. Persist a checkpoint after each final turn and state transition: stage, remaining active time, last committed event, room/candidate IDs and active recording segment.
2. On a classified transient media/provider failure, pause active time and establish one 120-second wall-clock recovery deadline. Use bounded backoff without concurrent duplicate requests.
3. On return, rebind tracks/participant as needed and resume the correct stage. Re-ask a cut-off question only when necessary and relate it to the original case instead of inventing duplicate evidence.
4. Do not replay HR after a technical outage, reset the stage to five minutes, or repeat handoff on duplicate reconnect events.
5. On timeout, preserve partial evidence and mark conversation incomplete with a reason. Distinguish permanent key/config errors from transient failures.
6. Implement startup reconciliation for interrupted states and expired leases. Record a new connection attempt if the previous room no longer exists; never claim its new SID is the old live room.
7. Implement expiry at interview start + 30 UTC days, a local scheduler and startup catch-up. Verify scheduler installation under the user's permissions.
8. Exclude expired records from reads immediately. Use a retryable deletion workflow/manifest to remove audio, snapshots, associated rows, derived exports, temp files and candidate-bearing logs.
9. Coordinate cleanup with task workers: expired tasks cannot be claimed, running expired tasks must not recreate deleted results, and late callbacks cannot resurrect expired records. Test this race explicitly.
10. Validate owned paths and do not follow arbitrary paths/symlinks into unrelated files. Retry file deletion failures visibly. Do not create an unmanaged backup.

## Deliverables

- Recovery use case/adapters, checkpoints and startup reconciliation.
- Cleanup entrypoint, local scheduler instructions and retryable deletion state.
- Fake-clock and failure-injection tests, including cleanup/worker races.

## Acceptance gate

- Return within the recovery budget resumes the right stage and remaining time.
- Timeout preserves an incomplete interview without fabricated missing evidence.
- Recent interviews remain intact while expired rows/files disappear.
- Running scoring cannot repopulate data after expiry.
- Cleanup catches up after downtime and reports physical deletion failures; the app does not promise deletion while the machine is off.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P08: Recovery, restart and 30-day retention. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
