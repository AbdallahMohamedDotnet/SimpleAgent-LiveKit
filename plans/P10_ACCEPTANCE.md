# P10 — End-to-end acceptance and Ubuntu runbook

Implementation: **IN_PROGRESS**. Verification: **BLOCKED**. Updated 21 September 2026.

**Read first:** [AGENTS.md](../AGENTS.md), [MAIN_PLAN.md](../MAIN_PLAN.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PROGRESS.md](../PROGRESS.md).

**Dependencies:** All previous phases; live gates require actual devices and credentials.

**Requirements covered:** R01–R19.

## Current state

The Ubuntu runbook, R01–R19 acceptance matrix, and aggregate provider-free smoke are implemented.
The smoke exercises the ordered fake lifecycle plus real temporary SQLite scoring,
recovery/retention, and localhost HTTP results workflows. The complete offline quality baseline
passes Ruff formatting/lint, strict mypy for 55 source files, and 40 pytest tests. This is not
end-to-end voice acceptance: the production ROOM Agent Server/controller and terminal RTC client
are absent, while physical audio and provider credentials/access remain blocked or unverified.

## Objective and scope

Prove the full local workflow and deliver reproducible operating instructions. Do not confuse lint success, fake-provider success or console-mode success with a completed room-based voice interview.

## Implementation tasks

1. Run formatting/lint/type checks, meaningful unit/contract/integration suites and the import-boundary check. Fix concrete failures; do not weaken gates.
2. Run a real terminal-audio interview in the local room using the two distinct voices and required providers. Record versions, stage/session references, room identity and stage transitions.
3. Deliberately delay HR assessment and confirm technical conversation continues. Check final independent scores, coverage and every cited evidence reference.
4. Verify deadline crossing during an answer, no subsequent question, barge-in, five-second idle and requested thinking time.
5. Exercise reconnect within and beyond 120 seconds, provider transient failure, permanent bad configuration, worker restart, malformed assessment and partial recordings.
6. Test duplicate candidate names and a second active-interview request. Ensure neither corrupts another record.
7. Advance a test clock to exercise retention, including worker/cleanup races and failed file deletion; verify old data is hidden and new data remains.
8. Calibrate HR/technical assessment on synthetic strong, weak, assisted and incomplete evidence. Record limitations of the short screening format.
9. Review SOLID boundaries: controller contains no SQL/HTML/provider construction; domain/application import restrictions hold; fakes obey contracts; resources have explicit owners.
10. Write docs/RUNBOOK.md with tested exact installation/configuration commands, startup order, CLI invocation, device selection, results URL, cleanup scheduling, recovery, shutdown and troubleshooting.
11. Write docs/ACCEPTANCE.md mapping every R01–R19 requirement to evidence, with PASSED/FAILED/BLOCKED status. Update PROGRESS.md and do not label skipped live checks as passes.

## Deliverables

- Runnable local application and a pinned toolchain.
- Tested Ubuntu runbook, acceptance matrix and concise known-limitations report.
- Clean final quality checks and honest separation of fake/live verification.

## Acceptance gate

- All MAIN_PLAN.md final acceptance items are evidenced or explicitly blocked; completion cannot be claimed while required live gates remain blocked.
- The operator can start the local server/agent/worker/results workflow and run an interview with name-only input.
- Same-room two-session handoff, parallel HR scoring, persistence, recovery and retention work end to end.
- No source secrets, real-candidate test fixtures, undocumented provider substitutions or unnecessary cloud dependencies remain.

## Engineering review

Apply AGENTS.md to this phase. Keep business rules in domain/application code, infrastructure in adapters and construction in bootstrap. Use typed contracts and meaningful behavioral tests. Preserve cancellation, resource ownership, idempotency and accurate failure reporting. Do not introduce unused abstractions or expand the product scope.

## Handoff to the next phase

Update PROGRESS.md with implementation status, verification status, changed files, commands actually run, evidence and unresolved risks. Clearly distinguish tested behavior from assumptions. Do not mark this phase complete simply because its files exist.

## Codex task prompt

> Implement P10: End-to-end acceptance and Ubuntu runbook. Read the repository instructions and this subplan first. Verify prerequisites, implement the smallest complete changes satisfying its acceptance gate, and run relevant checks. Follow SOLID and the dependency rules in AGENTS.md and ARCHITECTURE.md. Preserve all fixed requirements. Record actual results and blockers in PROGRESS.md. If assigned only this phase, stop after its completion report; if assigned the whole project, continue to the next ready phase. Never present unverified live behavior as tested.
